<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class WhatsAppService
{
    public function send(string $phone, string $code): void
    {
        abort_unless(config('services.whatsapp.token') && config('services.whatsapp.phone_id'), 422, 'Fournisseur WhatsApp non configuré.');
        Http::withToken(config('services.whatsapp.token'))->timeout(15)->post(
            'https://graph.facebook.com/'.config('services.whatsapp.version').'/'.config('services.whatsapp.phone_id').'/messages',
            ['messaging_product' => 'whatsapp', 'to' => ltrim($phone, '+'), 'type' => 'template', 'template' => [
                'name' => config('services.whatsapp.template'), 'language' => ['code' => 'fr'],
                'components' => [['type' => 'body', 'parameters' => [['type' => 'text', 'text' => $code]]], ['type' => 'button', 'sub_type' => 'url', 'index' => '0', 'parameters' => [['type' => 'text', 'text' => $code]]]],
            ]]
        )->throw();
    }
}
