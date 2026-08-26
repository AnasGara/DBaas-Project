<?php

namespace App\Http\Middleware;

use App\Models\User;
use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class ApiToken
{
    public function handle(Request $request, Closure $next)
    {
        $token = $request->bearerToken();
        abort_unless($token, 401, 'Connexion requise.');
        $record = DB::table('api_tokens')->where('hash', hash('sha256', $token))->where('expires_at', '>', now())->first();
        abort_unless($record, 401, 'Session expirée.');
        $user = User::find($record->user_id);
        abort_unless($user && $user->status === 'active', 403, 'Compte non actif.');
        $request->setUserResolver(fn () => $user);
        $request->attributes->set('token_id', $record->id);

        return $next($request);
    }
}
