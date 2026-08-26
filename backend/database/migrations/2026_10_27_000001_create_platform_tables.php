<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $t) {
            $t->string('role')->default('client');
            $t->string('status')->default('pending');
            $t->string('phone')->nullable();
            $t->timestamp('phone_verified_at')->nullable();
        });
        Schema::create('api_tokens', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained()->cascadeOnDelete();
            $t->string('hash', 64)->unique();
            $t->timestamp('expires_at');
            $t->timestamps();
        });
        Schema::create('mfa_challenges', function (Blueprint $t) {
            $t->uuid('id')->primary();
            $t->foreignId('user_id')->constrained()->cascadeOnDelete();
            $t->string('code_hash');
            $t->string('channel');
            $t->unsignedTinyInteger('attempts')->default(0);
            $t->timestamp('expires_at');
            $t->timestamp('consumed_at')->nullable();
            $t->timestamps();
        });
        Schema::create('database_instances', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained();
            $t->string('name');
            $t->string('engine');
            $t->string('version');
            $t->string('mode');
            $t->unsignedInteger('cpu');
            $t->unsignedInteger('ram');
            $t->unsignedInteger('storage');
            $t->string('datacenter');
            $t->string('plan');
            $t->string('status')->default('pending');
            $t->unsignedTinyInteger('usage')->default(0);
            $t->timestamp('activated_at')->nullable();
            $t->timestamps();
            $t->unique(['user_id', 'name']);
        });
        Schema::create('resource_requests', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained();
            $t->foreignId('database_id')->constrained('database_instances');
            $t->string('name');
            $t->string('type');
            $t->unsignedInteger('cpu');
            $t->unsignedInteger('ram');
            $t->unsignedInteger('storage');
            $t->string('status')->default('pending');
            $t->foreignId('reviewed_by')->nullable()->constrained('users');
            $t->timestamp('reviewed_at')->nullable();
            $t->timestamps();
        });
        Schema::create('backups', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained();
            $t->foreignId('database_id')->constrained('database_instances');
            $t->string('name');
            $t->string('date');
            $t->string('size');
            $t->string('site');
            $t->string('status');
            $t->timestamp('expires_at');
            $t->timestamps();
        });
        Schema::create('resource_allocations', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained();
            $t->foreignId('database_id')->constrained('database_instances');
            $t->string('name');
            $t->string('plan');
            $t->decimal('monthly_rate', 12, 4);
            $t->timestamp('starts_at');
            $t->timestamp('ends_at')->nullable();
            $t->timestamps();
        });
        Schema::create('invoices', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->constrained();
            $t->string('period');
            $t->string('number')->nullable()->unique();
            $t->json('lines');
            $t->decimal('total', 12, 2);
            $t->timestamp('emailed_at')->nullable();
            $t->timestamps();
            $t->unique(['user_id', 'period']);
        });
        Schema::create('audit_events', function (Blueprint $t) {
            $t->id();
            $t->foreignId('user_id')->nullable()->constrained();
            $t->string('action');
            $t->json('context');
            $t->timestamps();
        });
    }

    public function down(): void
    {
        foreach (['audit_events', 'invoices', 'resource_allocations', 'backups', 'resource_requests', 'database_instances', 'mfa_challenges', 'api_tokens'] as $table) {
            Schema::dropIfExists($table);
        }
        Schema::table('users', fn (Blueprint $t) => $t->dropColumn(['role', 'status', 'phone', 'phone_verified_at']));
    }
};
