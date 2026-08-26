<?php

use App\Http\Controllers\AuthController;
use App\Http\Controllers\InvoiceController;
use App\Http\Controllers\PlatformController;
use Illuminate\Support\Facades\Route;

Route::get('/health', fn () => ['status' => 'ok', 'cloud' => 'simulated']);
Route::middleware('throttle:auth')->group(function () {
    Route::post('/register', [AuthController::class, 'register']);
    Route::post('/login', [AuthController::class, 'login']);
    Route::post('/mfa/verify', [AuthController::class, 'verify']);
});
Route::middleware(['api.token', 'throttle:platform'])->group(function () {
    Route::post('/logout', [AuthController::class, 'logout']);
    Route::post('/mfa/whatsapp/enroll', [AuthController::class, 'enrollPhone'])->middleware('throttle:auth');
    Route::post('/mfa/whatsapp/verify', [AuthController::class, 'verifyPhone'])->middleware('throttle:auth');
    Route::get('/databases', [PlatformController::class, 'databases']);
    Route::post('/databases', [PlatformController::class, 'create']);
    Route::get('/resource-requests', [PlatformController::class, 'requests']);
    Route::post('/resource-requests', [PlatformController::class, 'extend']);
    Route::patch('/resource-requests/{id}', [PlatformController::class, 'review']);
    Route::get('/backups', [PlatformController::class, 'backups']);
    Route::post('/databases/{id}/backups', [PlatformController::class, 'backup']);
    Route::get('/admin/users', [PlatformController::class, 'users']);
    Route::post('/admin/users/{id}/approve', [PlatformController::class, 'activate']);
    Route::get('/invoices', [InvoiceController::class, 'index']);
    Route::get('/invoices/current/pdf', [InvoiceController::class, 'current']);
    Route::get('/invoices/{id}/pdf', [InvoiceController::class, 'download']);
});
