# Souverain Cloud — plateforme DBaaS

MVP React 19 + Laravel 12, interface française, avec espaces client et administrateur. Le dépôt contient une console interactive et une API persistante : le provisionnement et les sauvegardes cloud sont **simulés**. Aucun serveur de base de données client n’est créé par cette version.

## Démarrage local

Prérequis : Node 20.19+ recommandé (Node 20.18 testé ici), PHP 8.2+, Composer, extensions PHP `pdo_sqlite`, `mbstring`, `dom`, `fileinfo`, `gd` et `zip`.

Dans un premier terminal PowerShell :

```powershell
cd backend
composer install
Copy-Item .env.example .env  # installation initiale seulement
php artisan key:generate
New-Item -ItemType File -Force database/database.sqlite
php artisan migrate
php artisan serve --host=127.0.0.1 --port=8000
```

Dans un deuxième terminal :

```powershell
cd frontend
npm ci
npm run dev
```

Ouvrir [la console locale](http://localhost:5173). Vite relaie `/api` vers Laravel. Le mode démo est utilisable sans connexion et conserve uniquement ses données fictives dans le navigateur. Il permet de tester création → demande → vue administrateur démo → approbation. Le bouton de vue admin démo ne confère aucun droit dans l’API.

## Utiliser les comptes et l’API

```powershell
cd backend
php artisan platform:admin admin@example.test
```

Le mot de passe est saisi dans le terminal sans affichage. Aucun identifiant administrateur par défaut n’est livré. Cliquer sur le profil dans la console pour se connecter ou créer un compte client. Un administrateur doit ensuite activer chaque nouveau compte depuis **Administration**.

Par défaut, `MAIL_MAILER=log` : les codes MFA sont écrits dans `backend/storage/logs/laravel.log`, aucun message n’est envoyé. Pour un déploiement réel, configurer le SMTP souverain dans `.env`. Ne pas utiliser le transport `log` en production, car il contient les codes de connexion.

Les jetons aléatoires sont conservés en session navigateur, expirent après 8 heures et sont hachés côté serveur. Les codes MFA expirent après 5 minutes, sont hachés, limités à 5 essais et consommés une seule fois. Les routes d’authentification sont limitées à 10 requêtes/minute/IP. L’API vérifie le statut et les droits à chaque requête.

### WhatsApp

Configurer `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_GRAPH_VERSION` et un template d’authentification approuvé `WHATSAPP_AUTH_TEMPLATE`. Le template utilise un paramètre de code dans le corps et un bouton URL/copie du code. Depuis **Sécurité & accès**, un client connecté reçoit un code sur son numéro puis le vérifie. Les challenges de vérification du téléphone ne permettent pas de créer un jeton de connexion. WhatsApp est refusé sans fournisseur configuré et numéro vérifié. Vérifier le contrat de souveraineté et de traitement des données du fournisseur choisi avant activation.

## Périmètre implémenté

| Fonction | État |
|---|---|
| PostgreSQL, MySQL, Redis ; instance ou cluster 3 nœuds | Configuration, validation et persistance ; infrastructure simulée |
| Choix CPU, RAM, stockage et site | Validations serveur et approbation administrateur |
| Extensions | Augmentation uniquement, une demande en attente par base |
| Sauvegardes vers un site distinct | Métadonnées simulées ; cible et rétention 30 jours enregistrées |
| Trois datacenters | Paris, Lyon, Marseille sont des emplacements de démonstration à remplacer |
| Comptes client | Inscription, activation admin, isolation des données |
| MFA email | Implémenté, transport SMTP à configurer |
| MFA WhatsApp | Vérification de propriété et adaptateur d’envoi ; fournisseur à configurer |
| Dashboard client / admin | Ressources allouées persistantes, courbes CPU/RAM et états des sites fictifs |
| PAYG et packs 1/3/6/12 mois | Formules et remises persistantes ; calcul mensuel au prorata des allocations |
| PDF | Estimation du mois courant et factures immuables des mois clôturés |
| Emails mensuels | Commande planifiée le 1er à 08:00 UTC, transport mail à configurer |
| Audit | Création, extension, approbation, activation et sauvegarde |

## Facturation

Tarifs HT fictifs : `8 € / vCPU + 2 € / Go RAM + 0,10 € / Go SSD` par mois et par nœud, multipliés par trois pour un cluster. Remises packs : 1 mois 0 %, 3 mois 5 %, 6 mois 10 %, 12 mois 15 %. Une allocation ne commence à être comptée qu’à l’approbation. Une extension clôt l’allocation précédente et ouvre la suivante. Le montant est calculé en secondes, au prorata de la durée réelle du mois, puis arrondi en centimes par ligne.

Les packs sont ici des **tarifs mensuels remisés**, pas un prépaiement ni un engagement contractuel appliqué. La durée d’engagement, les renouvellements, les paiements, la TVA et les mentions légales commerciales restent à implémenter. Les PDF portent la mention « démonstration ». Les calculs portent sur des allocations simulées, pas sur une télémétrie cloud réelle.

```powershell
php artisan platform:invoices                 # mois précédent
php artisan platform:invoices --period=2026-09
php artisan schedule:work                    # développement
```

Le scheduler doit tourner en continu ou `schedule:run` être exécuté chaque minute par cron. Une facture est unique par client et période ; une nouvelle exécution conserve son instantané et ignore les emails déjà marqués envoyés. Une panne entre acceptation SMTP et enregistrement peut occasionner un doublon d’email ; prévoir un fournisseur avec clé d’idempotence pour la production.

## Vérification

```powershell
cd backend
php artisan test
vendor/bin/pint --test
cd ../frontend
npm run build
```

Les tests utilisent SQLite en mémoire. Ils couvrent l’isolation des clients, les approbations, les extensions, les sauvegardes simulées, le MFA, l’expiration et la révocation des jetons, les remises et l’immutabilité des factures, ainsi que les autorisations PDF.

## Déploiement conteneurisé

Une base Docker Compose est fournie : Nginx pour React, Apache/PHP pour Laravel, PostgreSQL pour les métadonnées et un scheduler séparé. Sa syntaxe a été validée ; les conteneurs n’ont pas été exécutés, car le moteur Docker Desktop est arrêté dans cet environnement.

```powershell
Copy-Item .env.deploy.example .env
# Renseigner APP_KEY (php artisan key:generate --show), DB_PASSWORD et SMTP.
docker compose up --build -d
docker compose exec api php artisan platform:admin admin@votre-domaine.fr
```

La console est publiée uniquement sur [127.0.0.1:8080](http://127.0.0.1:8080). Terminer TLS sur un reverse proxy avant toute exposition réseau. Les services attendent la disponibilité de PostgreSQL et la réussite des migrations. Les polices sont incluses dans le bundle, sans appel Google Fonts.

## Raccordement cloud avant production

Remplacer la frontière de simulation dans `PlatformController::review` et `backup` par des jobs idempotents exécutant les API privées du fournisseur (ou un opérateur Kubernetes adapté). Le statut `running` doit être publié seulement après confirmation réelle. Ajouter les secrets dans un coffre, les réseaux privés et ACL, la gestion TLS des moteurs, la collecte Prometheus, les sauvegardes chiffrées, la restauration vérifiée, les politiques de rétention et le contrôle des quotas physiques par site.

`CLOUD_SIMULATION=false` bloque les approbations et les sauvegardes tant qu’aucun adaptateur réel n’existe. Cette version ne revendique aucune certification de sécurité, résidence vérifiée des données, disponibilité contractuelle, RPO ou RTO. Aucun déploiement externe n’a été effectué.

Références : [Laravel 12](https://laravel.com/framework/docs/12.x/installation), [React avec Vite](https://react.dev/learn/build-a-react-app-from-scratch).
