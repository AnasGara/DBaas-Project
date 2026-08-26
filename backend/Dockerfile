FROM php:8.3-apache
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev libpng-dev libonig-dev libxml2-dev libzip-dev unzip \
    && docker-php-ext-install pdo_pgsql mbstring gd dom zip bcmath \
    && a2enmod rewrite headers \
    && rm -rf /var/lib/apt/lists/*
COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer
WORKDIR /var/www/html
COPY . .
RUN composer install --no-dev --no-interaction --prefer-dist --optimize-autoloader --no-scripts \
    && php artisan package:discover \
    && chown -R www-data:www-data storage bootstrap/cache \
    && sed -i 's|/var/www/html|/var/www/html/public|g' /etc/apache2/sites-available/000-default.conf
EXPOSE 80
