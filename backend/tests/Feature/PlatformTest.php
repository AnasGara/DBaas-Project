<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\BillingService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Str;
use Tests\TestCase;

class PlatformTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Cache::flush();
    }

    private function account(string $role = 'client'): array
    {
        $user = User::factory()->create(['role' => $role, 'status' => 'active']);
        $token = Str::random(80);
        DB::table('api_tokens')->insert(['user_id' => $user->id, 'hash' => hash('sha256', $token), 'expires_at' => now()->addHour()]);

        return [$user, ['Authorization' => 'Bearer '.$token]];
    }

    private function payload(): array
    {
        return ['name' => 'production-db', 'engine' => 'PostgreSQL', 'mode' => 'cluster', 'cpu' => 4, 'ram' => 16, 'storage' => 100, 'datacenter' => 'Paris · DC1', 'plan' => '3'];
    }

    public function test_registration_is_pending_and_cannot_self_assign_admin(): void
    {
        $this->postJson('/api/register', ['name' => 'Client', 'email' => 'client@example.test', 'password' => 'VeryStrong12345', 'role' => 'admin', 'status' => 'active'])->assertCreated();
        $this->assertDatabaseHas('users', ['email' => 'client@example.test', 'role' => 'client', 'status' => 'pending']);
        $this->postJson('/api/login', ['email' => 'client@example.test', 'password' => 'VeryStrong12345', 'channel' => 'email'])->assertForbidden();
    }

    public function test_tenant_isolation_approval_and_extension(): void
    {
        [$owner,$headers] = $this->account();
        [$other,$otherHeaders] = $this->account();
        [$admin,$adminHeaders] = $this->account('admin');
        $db = $this->postJson('/api/databases', $this->payload(), $headers)->assertCreated()->assertJsonPath('status', 'pending')->json();
        $this->getJson('/api/databases', $otherHeaders)->assertExactJson([]);
        $request = DB::table('resource_requests')->first();
        $this->patchJson('/api/resource-requests/'.$request->id, ['status' => 'approved'], $headers)->assertForbidden();
        $this->patchJson('/api/resource-requests/'.$request->id, ['status' => 'approved'], $adminHeaders)->assertOk();
        $this->assertDatabaseHas('database_instances', ['id' => $db['id'], 'status' => 'running']);
        $this->patchJson('/api/resource-requests/'.$request->id, ['status' => 'approved'], $adminHeaders)->assertConflict();
        $this->postJson('/api/resource-requests', ['database_id' => $db['id'], 'cpu' => 8, 'ram' => 32, 'storage' => 200], $otherHeaders)->assertNotFound();
        $this->postJson('/api/resource-requests', ['database_id' => $db['id'], 'cpu' => 2, 'ram' => 16, 'storage' => 100], $headers)->assertUnprocessable();
        $req = $this->postJson('/api/resource-requests', ['database_id' => $db['id'], 'cpu' => 8, 'ram' => 32, 'storage' => 200], $headers)->assertCreated()->json();
        $this->postJson('/api/resource-requests', ['database_id' => $db['id'], 'cpu' => 8, 'ram' => 32, 'storage' => 200], $headers)->assertConflict();
        $this->patchJson('/api/resource-requests/'.$req['id'], ['status' => 'approved'], $adminHeaders)->assertOk();
        $this->assertDatabaseHas('database_instances', ['id' => $db['id'], 'cpu' => 8]);
        $this->postJson('/api/databases/'.$db['id'].'/backups', [], $otherHeaders)->assertNotFound();
        $this->postJson('/api/databases/'.$db['id'].'/backups', [], $headers)->assertCreated()->assertJsonPath('site', 'Lyon · DC2')->assertJsonPath('status', 'Simulée');
        $this->assertDatabaseCount('resource_allocations', 2);
        $this->getJson('/api/invoices/current/pdf', $headers)->assertOk()->assertHeader('content-type', 'application/pdf');
    }

    public function test_mfa_codes_are_single_use_expiring_and_attempt_limited(): void
    {
        [$user] = $this->account();
        $id = (string) Str::uuid();
        DB::table('mfa_challenges')->insert(['id' => $id, 'user_id' => $user->id, 'code_hash' => Hash::make('123456'), 'channel' => 'email', 'expires_at' => now()->addMinutes(5)]);
        $result = $this->postJson('/api/mfa/verify', ['challenge_id' => $id, 'code' => '123456'])->assertOk()->assertJsonStructure(['token', 'user'])->json();
        $this->assertDatabaseMissing('api_tokens', ['hash' => $result['token']]);
        $this->postJson('/api/mfa/verify', ['challenge_id' => $id, 'code' => '123456'])->assertUnprocessable();
        $this->getJson('/api/databases', ['Authorization' => 'Bearer '.$result['token']])->assertOk();
        $this->postJson('/api/logout', [], ['Authorization' => 'Bearer '.$result['token']])->assertOk();
        $this->getJson('/api/databases', ['Authorization' => 'Bearer '.$result['token']])->assertUnauthorized();
        $expired = (string) Str::uuid();
        DB::table('mfa_challenges')->insert(['id' => $expired, 'user_id' => $user->id, 'code_hash' => Hash::make('123456'), 'channel' => 'email', 'expires_at' => now()->subMinute()]);
        $this->postJson('/api/mfa/verify', ['challenge_id' => $expired, 'code' => '123456'])->assertUnprocessable();
        $locked = (string) Str::uuid();
        DB::table('mfa_challenges')->insert(['id' => $locked, 'user_id' => $user->id, 'code_hash' => Hash::make('123456'), 'channel' => 'email', 'attempts' => 4, 'expires_at' => now()->addMinutes(5)]);
        $this->postJson('/api/mfa/verify', ['challenge_id' => $locked, 'code' => '654321'])->assertUnprocessable();
        $this->assertDatabaseHas('mfa_challenges', ['id' => $locked, 'attempts' => 5]);
        $this->postJson('/api/mfa/verify', ['challenge_id' => $locked, 'code' => '123456'])->assertUnprocessable();
    }

    public function test_invoices_are_immutable_discounted_and_owned(): void
    {
        [$user,$headers] = $this->account();
        [$other,$otherHeaders] = $this->account();
        $db = $this->postJson('/api/databases', $this->payload(), $headers)->assertCreated()->json();
        DB::table('resource_allocations')->insert(['user_id' => $user->id, 'database_id' => $db['id'], 'name' => 'production-db', 'plan' => '3', 'monthly_rate' => 100, 'starts_at' => '2026-09-01 00:00:00', 'ends_at' => '2026-10-01 00:00:00']);
        $billing = app(BillingService::class);
        $invoice = $billing->issue($user->id, '2026-09');
        $this->assertEquals(95, (float) $invoice->total);
        DB::table('resource_allocations')->update(['monthly_rate' => 200]);
        $this->assertEquals(95, (float) $billing->issue($user->id, '2026-09')->total);
        $this->assertDatabaseCount('invoices', 1);
        $this->getJson('/api/invoices/'.$invoice->id.'/pdf', $otherHeaders)->assertNotFound();
        $this->getJson('/api/invoices/'.$invoice->id.'/pdf', $headers)->assertOk()->assertHeader('content-type', 'application/pdf');
    }

    public function test_login_sends_email_challenge_without_exposing_code(): void
    {
        Mail::fake();
        User::factory()->create(['email' => 'login@example.test', 'password' => 'VeryStrong12345', 'status' => 'active']);
        $this->postJson('/api/login', ['email' => 'login@example.test', 'password' => 'VeryStrong12345', 'channel' => 'email'])->assertOk()->assertJsonStructure(['challenge_id', 'expires_in'])->assertJsonMissingPath('code');
        $this->assertDatabaseCount('mfa_challenges',1);
        $this->postJson('/api/login',['email' => 'login@example.test', 'password' => 'VeryStrong12345', 'channel' => 'whatsapp'])->assertUnprocessable();
    }
}
