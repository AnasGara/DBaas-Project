<?php

namespace App\Services;

use Barryvdh\DomPDF\Facade\Pdf;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

class BillingService
{
    public function lines(int $userId, string $period, bool $current = false): array
    {
        $start = CarbonImmutable::parse($period.'-01')->startOfMonth();
        $end = $start->addMonth();
        if ($current && now()->lt($end)) {
            $end = CarbonImmutable::now();
        }
        $secondsInMonth = $start->diffInSeconds($start->addMonth());

        return DB::table('resource_allocations')->where('user_id', $userId)->where('starts_at', '<', $end)
            ->where(fn ($q) => $q->whereNull('ends_at')->orWhere('ends_at', '>', $start))->get()->map(function ($a) use ($start, $end, $secondsInMonth) {
                $from = CarbonImmutable::parse($a->starts_at)->max($start);
                $until = $a->ends_at ? CarbonImmutable::parse($a->ends_at)->min($end) : $end;
                $seconds = max(0, $from->diffInSeconds($until, false));
                $discount = ['payg' => 0, '1' => 0, '3' => .05, '6' => .10, '12' => .15][$a->plan] ?? 0;

                return ['name' => $a->name, 'plan' => $a->plan, 'hours' => round($seconds / 3600, 4), 'monthly_rate' => (float) $a->monthly_rate, 'discount' => $discount, 'amount' => round($a->monthly_rate * (1 - $discount) * $seconds / $secondsInMonth, 2)];
            })->all();
    }

    public function issue(int $userId, string $period): object
    {
        // Immutable snapshot per customer and period; scheduler retries reuse it.
        return DB::transaction(function () use ($userId, $period) {
            DB::table('users')->where('id', $userId)->lockForUpdate()->first();
            $existing = DB::table('invoices')->where('user_id', $userId)->where('period', $period)->first();
            if ($existing) {
                return $existing;
            }
            $lines = $this->lines($userId, $period);
            $id = DB::table('invoices')->insertGetId(['user_id' => $userId, 'period' => $period, 'lines' => json_encode($lines), 'total' => array_sum(array_column($lines, 'amount')), 'created_at' => now(), 'updated_at' => now()]);
            DB::table('invoices')->where('id', $id)->update(['number' => 'SC-'.str_replace('-', '', $period).'-'.str_pad((string) $id, 6, '0', STR_PAD_LEFT)]);

            return DB::table('invoices')->find($id);
        });
    }

    public function pdf(object $invoice, object $user, bool $estimate = false)
    {
        return Pdf::loadView('invoice', ['invoice' => $invoice, 'customer' => $user, 'lines' => is_string($invoice->lines) ? json_decode($invoice->lines, true) : $invoice->lines, 'estimate' => $estimate])->setPaper('a4');
    }
}
