<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class WhatsAppTest extends TestCase
{
    use RefreshDatabase;

    public function test_enrollment_proves_ownership_and_cannot_issue_a_login_token(): void
    {
        Cache::flush();
        $user = User::factory()->create(['status' => 'active']);
        $other = User::factory()->create(['status' => 'active']);
        foreach ([$user, $other] as $u) {
            DB::table('api_tokens')->insert(['user_id' => $u->id, 'hash' => hash('sha256', 'test-'.$u->id), 'expires_at' => now()->addHour()]);
        }
        $headers = ['Authorization' => 'Bearer test-'.$user->id];
        $otherHeaders = ['Authorization' => 'Bearer test-'.$other->id];
        config(['services.whatsapp.token' => 'test-token', 'services.whatsapp.phone_id' => 'test-id']);
        Http::fake(['graph.facebook.com/*' => Http::response(['messages' => [['id' => 'test-message']]], 200)]);
        $challenge = $this->postJson('/api/mfa/whatsapp/enroll', ['phone' => '+33612345678'], $headers)->assertOk()->json('challenge_id');
        $code = Http::recorded()[0][0]['template']['components'][0]['parameters'][0]['text'];
        $this->postJson('/api/mfa/verify', ['challenge_id' => $challenge, 'code' => $code])->assertUnprocessable();
        $this->postJson('/api/mfa/whatsapp/verify', ['challenge_id' => $challenge, 'code' => $code], $otherHeaders)->assertUnprocessable();
        $this->postJson('/api/mfa/whatsapp/verify', ['challenge_id' => $challenge, 'code' => $code], $headers)->assertOk();
        $this->assertNotNull($user->fresh()->phone_verified_at);
        $this->assertEquals('+33612345678', $user->fresh()->phone);
        $this->postJson('/api/mfa/whatsapp/verify', ['challenge_id' => $challenge, 'code' => $code], $headers)->assertUnprocessable();
    }
}
