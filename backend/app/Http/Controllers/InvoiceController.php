<?php

namespace App\Http\Controllers;

use App\Models\User;
use App\Services\BillingService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class InvoiceController extends Controller
{
    public function index(Request $r)
    {
        $q = DB::table('invoices');
        if ($r->user()->role !== 'admin') {
            $q->where('user_id', $r->user()->id);
        }

        return $q->orderByDesc('period')->get();
    }

    public function current(Request $r, BillingService $billing)
    {
        $lines = $billing->lines($r->user()->id, now()->format('Y-m'), true);
        $invoice = (object) ['number' => 'ESTIMATION', 'period' => now()->format('Y-m'), 'lines' => $lines, 'total' => array_sum(array_column($lines, 'amount'))];

        return $billing->pdf($invoice, $r->user(), true)->download('estimation-'.now()->format('Y-m').'.pdf');
    }

    public function download(Request $r, int $id, BillingService $billing)
    {
        $q = DB::table('invoices')->where('id', $id);
        if ($r->user()->role !== 'admin') {
            $q->where('user_id', $r->user()->id);
        }
        $invoice = $q->first();
        abort_unless($invoice, 404);

        return $billing->pdf($invoice, User::findOrFail($invoice->user_id))->download($invoice->number.'.pdf');
    }
}
