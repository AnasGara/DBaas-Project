<?php

namespace App\Providers;

use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        //
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        RateLimiter::for('auth', fn ($request) => Limit::perMinute(10)->by('auth:'.$request->ip()));
        RateLimiter::for('platform', fn ($request) => Limit::perMinute(120)->by('platform:'.($request->user()?->id ?? $request->ip())));
    }
}
