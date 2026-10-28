Name:		grommunio-sync
Version:	2.7
Release:	1
Source0:	https://github.com/grommunio/grommunio-sync/archive/refs/tags/%{version}.tar.gz#/grommunio-sync-%{version}.tar.gz
Summary:	Exchange ActiveSync interface for grommunio
URL:		https://github.com/grommunio/grommunio-sync
License:	AGPL-3.0
Group:		Servers
BuildArch:	noarch

Requires:	php
Requires:	php-fpm
Requires:	php-gromox
Requires:	php-mbstring
Requires:	php-mysqli
Requires:	php-pcntl
Requires:	php-pdo
Requires:	php-posix
Requires:	php-soap
Requires:	php-redis
Requires:	grommunio-mapi-header-php >= 2.4
Requires:	gromox
Requires:	redis
Requires:	nginx

%description
grommunio-sync implements Exchange ActiveSync (EAS) for mobile devices
such as Android, iPhone and Outlook mobile. It talks to Gromox via
the PHP MAPI bindings.

Shared-mailbox impersonation uses the
impersonated-user!auth-user@domain.com login form.

This package ships a dedicated php-fpm instance (php-fpm@grommunio-sync),
a dedicated Redis instance (redis@grommunio-sync — not redis@grommunio),
and an nginx snippet in /etc/nginx/grommunio.d/. Enable the fpm instance
and reload nginx after install.

%prep
%autosetup -p1

%install
mkdir -p %{buildroot}%{_datadir}/%{name}
cp -a lib vendor index.php grommunio-sync-top.php grommunio-sync-top LICENSE README.rst \
	%{buildroot}%{_datadir}/%{name}/
# Static version (the git-describe fallback would always say "GIT")
cat >%{buildroot}%{_datadir}/%{name}/version.php <<EOF
<?php
define("GROMMUNIOSYNC_VERSION", "%{version}");
EOF

# Config in /etc, linked into the app tree
mkdir -p %{buildroot}%{_sysconfdir}/%{name}
sed -e "s|define('MAPI_SERVER', 'default:');|define('MAPI_SERVER', 'unix:/run/gromox/zcore.sock');|" \
    -e "s|define('REDIS_HOST', 'localhost');|define('REDIS_HOST', '/run/redis/grommunio-sync/redis.sock');|" \
    -e "s|define('REDIS_PORT', 6379);|define('REDIS_PORT', 0);|" \
	config.php >%{buildroot}%{_sysconfdir}/%{name}/config.php
ln -s %{_sysconfdir}/%{name}/config.php %{buildroot}%{_datadir}/%{name}/config.php

install -d %{buildroot}%{_sbindir}
ln -s %{_datadir}/%{name}/grommunio-sync-top.php %{buildroot}%{_sbindir}/grommunio-sync-top

# Logs
install -d -m 0770 %{buildroot}%{_localstatedir}/log/%{name}

# logrotate
install -d %{buildroot}%{_sysconfdir}/logrotate.d
cat >%{buildroot}%{_sysconfdir}/logrotate.d/%{name} <<EOF
%{_localstatedir}/log/%{name}/*.log {
	missingok
	notifempty
	sharedscripts
	su www www
}
EOF

# Dedicated php-fpm instance (OMV php-fpm@ runs as www)
install -d %{buildroot}%{_sysconfdir}/php-fpm-instances.d
cat >%{buildroot}%{_sysconfdir}/php-fpm-instances.d/grommunio-sync.conf <<'EOF'
[global]
error_log=syslog

[grommunio-sync]
user=www
group=www
listen=/run/php-fpm/grommunio-sync.sock
listen.owner=www
listen.group=www
listen.mode=0660

php_admin_value[error_log]=/var/log/grommunio-sync/php-fpm.log
php_admin_value[log_errors]=on
php_admin_value[memory_limit]=512M
php_admin_value[max_execution_time]=3660
php_admin_value[post_max_size]=102M
php_admin_value[upload_max_filesize]=100M

pm=dynamic
pm.max_children=50
pm.start_servers=1
pm.min_spare_servers=1
pm.max_spare_servers=12
request_terminate_timeout=3660s

env[GROMOX_CONFIG_DIR]=/etc/gromox
php_admin_value[open_basedir]=/usr/share/grommunio-sync:/etc/grommunio-sync:/var/log/grommunio-sync:/etc/gromox:/usr/share/php-mapi:/usr/share/php:/run/gromox:/run/redis/grommunio-sync
php_admin_value[opcache.enable]=0
php_admin_value[opcache.jit]=0
php_admin_value[mapi.zcore_socket]=/run/gromox/zcore.sock
EOF

cat >%{buildroot}%{_sysconfdir}/php-fpm-instances.d/grommunio-sync.env <<'EOF'
PHP_FPM_ARGS="-d extension=mapi.so -d extension=redis.so -d opcache.enable=0 -d opcache.jit=0 -d opcache.enable_cli=0"
EOF

# nginx snippet; grommunio-web includes /etc/nginx/grommunio.d/*.conf
install -d %{buildroot}%{_sysconfdir}/nginx/grommunio.d
cat >%{buildroot}%{_sysconfdir}/nginx/grommunio.d/sync.conf <<'EOF'
# Takes precedence over the gromox EAS proxy in the main server block.
location ^~ /Microsoft-Server-ActiveSync {
	include fastcgi_params;
	fastcgi_pass unix:/run/php-fpm/grommunio-sync.sock;
	fastcgi_param SCRIPT_FILENAME /usr/share/grommunio-sync/index.php;
	fastcgi_param HTTP_PROXY "";
	fastcgi_read_timeout 3660;
	fastcgi_param PHP_VALUE "memory_limit=512M
max_execution_time=3660
post_max_size=102M
upload_max_filesize=100M";
	client_max_body_size 102m;
}
EOF

# Dedicated Redis instance. grommunio-sync only uses Redis for its own
# IPC / top / device cache; admin-api reads those same keys for
# "sync top". This is not redis@grommunio.
install -d %{buildroot}%{_sysconfdir}/redis
cat >%{buildroot}%{_sysconfdir}/redis/grommunio-sync.conf <<'EOF'
# redis@grommunio-sync — per-application instance for grommunio-sync
bind 127.0.0.1 -::1
protected-mode yes
port 0
unixsocket /run/redis/grommunio-sync/redis.sock
unixsocketperm 666
pidfile /run/redis/grommunio-sync.pid
dir /srv/redis/grommunio-sync
dbfilename dump.rdb
logfile ""
loglevel notice
daemonize no
supervised systemd
timeout 0
tcp-keepalive 300
EOF

# Start redis with the fpm instance, and at boot
install -d %{buildroot}%{_unitdir}/php-fpm@grommunio-sync.service.d
cat >%{buildroot}%{_unitdir}/php-fpm@grommunio-sync.service.d/redis.conf <<'EOF'
[Unit]
Wants=redis@grommunio-sync.service
After=redis@grommunio-sync.service
EOF
install -d %{buildroot}%{_unitdir}/multi-user.target.wants
ln -s ../redis@.service %{buildroot}%{_unitdir}/multi-user.target.wants/redis@grommunio-sync.service

# Point admin-api at the same instance so /system/sync/top works
install -d %{buildroot}%{_sysconfdir}/grommunio-admin-api/conf.d
cat >%{buildroot}%{_sysconfdir}/grommunio-admin-api/conf.d/sync-redis.yaml <<'EOF'
sync:
  connection:
    unix_socket_path: /run/redis/grommunio-sync/redis.sock
EOF

%files
%{_datadir}/%{name}
%dir %{_sysconfdir}/%{name}
%config(noreplace) %{_sysconfdir}/%{name}/config.php
%{_sbindir}/grommunio-sync-top
%config(noreplace) %{_sysconfdir}/logrotate.d/%{name}
%config(noreplace) %{_sysconfdir}/php-fpm-instances.d/grommunio-sync.conf
%config(noreplace) %{_sysconfdir}/php-fpm-instances.d/grommunio-sync.env
%config(noreplace) %{_sysconfdir}/nginx/grommunio.d/sync.conf
%config(noreplace) %attr(0640,root,redis) %{_sysconfdir}/redis/grommunio-sync.conf
%{_unitdir}/php-fpm@grommunio-sync.service.d
%{_unitdir}/multi-user.target.wants/redis@grommunio-sync.service
%dir %{_sysconfdir}/grommunio-admin-api
%dir %{_sysconfdir}/grommunio-admin-api/conf.d
%config(noreplace) %{_sysconfdir}/grommunio-admin-api/conf.d/sync-redis.yaml
%dir %attr(0770,www,www) %{_localstatedir}/log/%{name}
