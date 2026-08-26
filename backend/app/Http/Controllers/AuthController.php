<?php

namespace App\Http\Controllers;

use App\Models\User;
use App\Services\WhatsAppService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;
use Illuminate\Validation\Rules\Password;

class AuthController extends Controller
{
    public function register(Request $request)
    {
        $data = $request->validate([
            'name' => 'required|string|max:120', 'email' => 'required|email|max:200|unique:users',
            'password' => ['required', Password::min(12)->letters()->numbers()],
            'phone' => ['nullable', 'regex:/^\+[1-9][0-9]{7,14}$/'],
        ]);
        User::create($data);

        return response()->json(['message' => 'Compte créé. Un administrateur doit valider votre activation.'], 201);
    }

    public function login(Request $request)
    {
        $data = $request->validate(['email' => 'required|email', 'password' => 'required|string', 'channel' => 'required|in:email,whatsapp']);
        $user = User::where('email', $data['email'])->first();
        abort_unless($user && Hash::check($data['password'], $user->password), 422, 'Identifiants incorrects.');
        abort_unless($user->status === 'active', 403, 'Votre compte attend la validation administrateur.');
        if ($data['channel'] === 'whatsapp') {
            abort_unless($user->phone && $user->phone_verified_at && config('services.whatsapp.token') && config('services.whatsapp.phone_id'), 422, 'WhatsApp nécessite un numéro vérifié et un fournisseur configuré.');
        }
        $code = (string) random_int(100000, 999999);
        $id = (string) Str::uuid();
        DB::table('mfa_challenges')->insert(['id' => $id, 'user_id' => $user->id, 'code_hash' => Hash::make($code), 'channel' => $data['channel'], 'expires_at' => now()->addMinutes(5), 'created_at' => now(), 'updated_at' => now()]);
        try {
            if ($data['channel'] === 'email') {
                Mail::raw("Votre code Souverain Cloud : {$code}. Il expire dans 5 minutes.", fn ($m) => $m->to($user->email)->subject('Votre code de connexion'));
            } else {
                app(WhatsAppService::class)->send($user->phone, $code);
            }
        } catch (\Throwable $e) {
            DB::table('mfa_challenges')->where('id', $id)->delete();
            report($e);
            abort(503, 'Envoi du code impossible. Vérifiez la configuration du fournisseur.');
        }

        return ['challenge_id' => $id, 'expires_in' => 300];
    }

    public function verify(Request $request)
    {
        $data = $request->validate(['challenge_id' => 'required|uuid', 'code' => 'required|digits:6']);
        // Return the failure from the transaction so failed attempts are committed.
        $result = DB::transaction(function () use ($data) {
            $challenge = DB::table('mfa_challenges')->where('id', $data['challenge_id'])->lockForUpdate()->first();
            if (! $challenge || $challenge->purpose !== 'login' || $challenge->consumed_at || $challenge->expires_at < now() || $challenge->attempts >= 5) {
                return null;
            }
            DB::table('mfa_challenges')->where('id', $challenge->id)->increment('attempts');
            if (! Hash::check($data['code'], $challenge->code_hash)) {
                return null;
            }
            $user = User::find($challenge->user_id);
            if (! $user || $user->status !== 'active') {
                return null;
            }
            DB::table('mfa_challenges')->where('id', $challenge->id)->update(['consumed_at' => now()]);
            if ($challenge->channel === 'email' && ! $user->email_verified_at) {
                $user->forceFill(['email_verified_at' => now()])->save();
            }
            $token = Str::random(80);
            DB::table('api_tokens')->insert(['user_id' => $user->id, 'hash' => hash('sha256', $token), 'expires_at' => now()->addHours(8), 'created_at' => now(), 'updated_at' => now()]);

            return ['token' => $token, 'user' => $user];
        });
        abort_unless($result, 422, 'Code invalide, expiré ou déjà utilisé.');

        return $result;
    }

    public function logout(Request $request)
    {
        DB::table('api_tokens')->where('id', $request->attributes->get('token_id'))->delete();

        return ['message' => 'Déconnexion effectuée.'];
    }

    public function enrollPhone(Request $request, WhatsAppService $whatsapp)
    {
        $data = $request->validate(['phone' => ['required', 'regex:/^\+[1-9][0-9]{7,14}$/']]);
        abort_unless(config('services.whatsapp.token') && config('services.whatsapp.phone_id'), 422, 'Fournisseur WhatsApp non configuré.');
        $code = (string) random_int(100000, 999999);
        $id = (string) Str::uuid();
        DB::table('mfa_challenges')->insert(['id' => $id, 'user_id' => $request->user()->id, 'code_hash' => Hash::make($code), 'channel' => 'whatsapp', 'purpose' => 'phone_verification', 'destination' => $data['phone'], 'expires_at' => now()->addMinutes(5), 'created_at' => now(), 'updated_at' => now()]);
        try {
            $whatsapp->send($data['phone'], $code);
        } catch (\Throwable $e) {
            DB::table('mfa_challenges')->where('id', $id)->delete();
            report($e);
            abort(503, 'Impossible d’envoyer le code WhatsApp.');
        }

        return ['challenge_id' => $id, 'expires_in' => 300];
    }

    public function verifyPhone(Request $request)
    {
        $data = $request->validate(['challenge_id' => 'required|uuid', 'code' => 'required|digits:6']);
        $user = DB::transaction(function () use ($request, $data) {
            $c = DB::table('mfa_challenges')->where('id', $data['challenge_id'])->where('user_id', $request->user()->id)->where('purpose', 'phone_verification')->lockForUpdate()->first();
            if (! $c || $c->consumed_at || $c->expires_at < now() || $c->attempts >= 5) {
                return null;
            }
            DB::table('mfa_challenges')->where('id', $c->id)->increment('attempts');
            if (! Hash::check($data['code'], $c->code_hash)) {
                return null;
            }
            DB::table('mfa_challenges')->where('id', $c->id)->update(['consumed_at' => now()]);
            $user = $request->user();
            $user->forceFill(['phone' => $c->destination, 'phone_verified_at' => now()])->save();
            DB::table('audit_events')->insert(['user_id' => $user->id, 'action' => 'phone.verified', 'context' => '{}', 'created_at' => now(), 'updated_at' => now()]);

            return $user;
        });
        abort_unless($user, 422, 'Code invalide, expiré ou déjà utilisé.');

        return ['user' => $user, 'message' => 'Numéro WhatsApp vérifié.'];
    }
}
