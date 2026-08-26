<?php

use App\Models\User;
use App\Services\BillingService;
use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Schedule;

Artisan::command('platform:admin {email} {--name=Administrateur}', function () {
    $email = $this->argument('email');
    if (! filter_var($email, FILTER_VALIDATE_EMAIL)) {
        $this->error('Email invalide.');

        return 1;
    }
    $password = $this->secret('Mot de passe (12 caractères minimum, lettres et chiffres)');
    if (strlen($password ?? '') < 12 || ! preg_match('/[a-zA-Z]/', $password) || ! preg_match('/[0-9]/', $password)) {
        $this->error('Mot de passe insuffisant.');

        return 1;
    }
    $user = User::firstOrNew(['email' => $email]);
    $user->forceFill(['name' => $this->option('name'), 'password' => $password, 'role' => 'admin', 'status' => 'active'])->save();
    $this->info('Compte administrateur prêt. La connexion exige un code MFA.');
});

Artisan::command('platform:invoices {--period=}', function () {
    $period = $this->option('period') ?: now()->subMonth()->format('Y-m');
    if (! preg_match('/^\d{4}-(0[1-9]|1[0-2])$/', $period) || $period >= now()->format('Y-m')) {
        $this->error('Une période mensuelle clôturée est requise (YYYY-MM).');

        return 1;
    }
    $billing = app(BillingService::class);
    foreach (User::where('role', 'client')->where('status', 'active')->cursor() as $user) {
        $invoice = $billing->issue($user->id, $period);
        if ($invoice->emailed_at) {
            continue;
        }
        try {
            $pdf = $billing->pdf($invoice, $user)->output();
            Mail::raw('Votre facture mensuelle Souverain Cloud est disponible en pièce jointe.', fn ($m) => $m->to($user->email)->subject('Facture '.$invoice->number)->attachData($pdf, $invoice->number.'.pdf', ['mime' => 'application/pdf']));
            DB::table('invoices')->where('id', $invoice->id)->update(['emailed_at' => now(), 'updated_at' => now()]);
            $this->info('Facture traitée : '.$invoice->number);
        } catch (Throwable $e) {
            report($e);
            $this->error('Échec d’envoi pour la facture '.$invoice->number);
        }
    }
})->purpose('Générer les factures du mois clôturé et les envoyer par email.');

Schedule::command('platform:invoices')->monthlyOn(1, '08:00')->withoutOverlapping();
Schedule::call(fn () => DB::table('api_tokens')->where('expires_at', '<', now())->delete())->daily();
Schedule::call(fn () => DB::table('mfa_challenges')->where('expires_at', '<', now()->subDay())->delete())->daily();

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');
