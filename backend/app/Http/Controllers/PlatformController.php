<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class PlatformController extends Controller
{
    private function scoped(Request $r, string $table)
    {
        $q = DB::table($table);

        return $r->user()->role === 'admin' ? $q : $q->where('user_id', $r->user()->id);
    }

    private function admin(Request $r): void
    {
        abort_unless($r->user()->role === 'admin', 403, 'Accès administrateur requis.');
    }

    private function audit(Request $r, string $action, array $context): void
    {
        DB::table('audit_events')->insert(['user_id' => $r->user()->id, 'action' => $action, 'context' => json_encode($context), 'created_at' => now(), 'updated_at' => now()]);
    }

    private function resources(Request $r): array
    {
        return $r->validate(['cpu' => 'required|integer|in:2,4,8,16,32,64', 'ram' => 'required|integer|in:8,16,32,64,128,256', 'storage' => 'required|integer|min:20|max:10000']);
    }

    public function databases(Request $r)
    {
        return $this->scoped($r, 'database_instances')->orderBy('id')->get();
    }

    public function requests(Request $r)
    {
        return $this->scoped($r, 'resource_requests')->latest()->get();
    }

    public function backups(Request $r)
    {
        return $this->scoped($r, 'backups')->latest()->get();
    }

    public function create(Request $r)
    {
        $data = array_merge($this->resources($r), $r->validate([
            'name' => ['required', 'regex:/^[a-z][a-z0-9-]{2,39}$/', Rule::unique('database_instances')->where('user_id', $r->user()->id)],
            'engine' => 'required|in:PostgreSQL,MySQL,Redis', 'mode' => 'required|in:single,cluster',
            'datacenter' => ['required', Rule::in(['Paris · DC1', 'Lyon · DC2', 'Marseille · DC3'])], 'plan' => 'required|in:payg,1,3,6,12',
        ]));

        return DB::transaction(function () use ($r, $data) {
            $id = DB::table('database_instances')->insertGetId([...$data, 'user_id' => $r->user()->id, 'version' => ['PostgreSQL' => '16.4', 'MySQL' => '8.4', 'Redis' => '7.4'][$data['engine']], 'created_at' => now(), 'updated_at' => now()]);
            DB::table('resource_requests')->insert(['user_id' => $r->user()->id, 'database_id' => $id, 'name' => $data['name'], 'type' => 'Création', 'cpu' => $data['cpu'], 'ram' => $data['ram'], 'storage' => $data['storage'], 'created_at' => now(), 'updated_at' => now()]);
            $this->audit($r, 'database.requested', ['database_id' => $id]);

            return response()->json(DB::table('database_instances')->find($id), 201);
        });
    }

    public function extend(Request $r)
    {
        $data = $this->resources($r);
        $r->validate(['database_id' => 'required|integer']);

        return DB::transaction(function () use ($r, $data) {
            $db = $this->scoped($r, 'database_instances')->where('id', $r->database_id)->lockForUpdate()->first();
            abort_unless($db, 404);
            abort_unless($db->status === 'running', 422, 'La base doit être disponible.');
            foreach (['cpu', 'ram', 'storage'] as $field) {
                abort_if($data[$field] < $db->$field, 422, 'Une extension ne peut pas réduire les ressources.');
            }
            abort_if($data['cpu'] == $db->cpu && $data['ram'] == $db->ram && $data['storage'] == $db->storage, 422, 'Choisissez au moins une augmentation de ressources.');
            abort_if(DB::table('resource_requests')->where('database_id', $db->id)->where('status', 'pending')->exists(), 409, 'Une demande est déjà en attente.');
            $id = DB::table('resource_requests')->insertGetId([...$data, 'user_id' => $db->user_id, 'database_id' => $db->id, 'name' => $db->name, 'type' => 'Extension', 'created_at' => now(), 'updated_at' => now()]);
            $this->audit($r, 'extension.requested', ['database_id' => $db->id]);

            return response()->json(DB::table('resource_requests')->find($id), 201);
        });
    }

    public function review(Request $r, int $id)
    {
        $this->admin($r);
        $r->validate(['status' => 'required|in:approved,rejected']);

        return DB::transaction(function () use ($r, $id) {
            $req = DB::table('resource_requests')->where('id', $id)->lockForUpdate()->first();
            abort_unless($req, 404);
            abort_unless($req->status === 'pending', 409, 'Cette demande a déjà été traitée.');
            $db = DB::table('database_instances')->where('id', $req->database_id)->lockForUpdate()->first();
            if ($r->status === 'approved') {
                // Simulator boundary: replace with an idempotent provider job before production.
                abort_unless(config('platform.simulation'), 503, 'Aucun adaptateur cloud actif.');
                DB::table('database_instances')->where('id', $db->id)->update(['cpu' => $req->cpu, 'ram' => $req->ram, 'storage' => $req->storage, 'status' => 'running', 'activated_at' => $db->activated_at ?? now(), 'updated_at' => now()]);
                DB::table('resource_allocations')->where('database_id', $db->id)->whereNull('ends_at')->update(['ends_at' => now(), 'updated_at' => now()]);
                $rate = ($req->cpu * 8 + $req->ram * 2 + $req->storage * .1) * ($db->mode === 'cluster' ? 3 : 1);
                DB::table('resource_allocations')->insert(['user_id' => $db->user_id, 'database_id' => $db->id, 'name' => $db->name, 'plan' => $db->plan, 'monthly_rate' => $rate, 'starts_at' => now(), 'created_at' => now(), 'updated_at' => now()]);
            } elseif ($req->type === 'Création') {
                DB::table('database_instances')->where('id', $db->id)->update(['status' => 'failed', 'updated_at' => now()]);
            }
            DB::table('resource_requests')->where('id', $id)->update(['status' => $r->status, 'reviewed_by' => $r->user()->id, 'reviewed_at' => now(), 'updated_at' => now()]);
            $this->audit($r, 'request.'.$r->status, ['request_id' => $id, 'simulated' => true]);

            return DB::table('resource_requests')->find($id);
        });
    }

    public function backup(Request $r, int $id)
    {
        $db = $this->scoped($r, 'database_instances')->where('id', $id)->first();
        abort_unless($db, 404);
        abort_unless($db->status === 'running', 422, 'La base doit être disponible.');
        abort_unless(config('platform.simulation'), 503, 'Aucun adaptateur de sauvegarde actif.');
        $site = $db->datacenter === 'Paris · DC1' ? 'Lyon · DC2' : ($db->datacenter === 'Lyon · DC2' ? 'Marseille · DC3' : 'Paris · DC1');
        $bid = DB::table('backups')->insertGetId(['database_id' => $id, 'user_id' => $db->user_id, 'name' => $db->name, 'date' => now()->format('d/m/Y H:i'), 'size' => 'Simulation', 'site' => $site, 'status' => 'Simulée', 'expires_at' => now()->addDays(30), 'created_at' => now(), 'updated_at' => now()]);
        $this->audit($r, 'backup.simulated', ['database_id' => $id, 'target' => $site]);

        return response()->json(DB::table('backups')->find($bid), 201);
    }

    public function users(Request $r)
    {
        $this->admin($r);

        return DB::table('users')->select('id', 'name', 'email', 'status', 'role')->where('role', 'client')->get();
    }

    public function activate(Request $r, int $id)
    {
        $this->admin($r);
        abort_unless(DB::table('users')->where('id', $id)->where('role', 'client')->exists(), 404);
        DB::table('users')->where('id',$id)->update(['status' => 'active', 'updated_at' => now()]);
        $this->audit($r,'account.activated',['client_id' => $id]);

        return ['message' => 'Compte activé.'];
    }
}
