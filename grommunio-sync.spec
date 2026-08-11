Name:		grommunio-sync
Version:	2.5
Release:	1
Source0:	https://github.com/grommunio/grommunio-sync/releases/download/%{version}/grommunio-sync-%{version}.tar.zst
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
Requires:	grommunio-mapi-header-php
Requires:	gromox
Requires:	redis
Requires:	nginx

%description
grommunio-sync implements Exchange ActiveSync (EAS) for mobile devices
such as Android, iPhone and Outlook mobile. It talks to Gromox via
the PHP MAPI bindings.

Shared-mailbox impersonation uses the
impersonated-user!auth-user@domain.com login form.

This package ships a dedicated php-fpm instance (php-fpm@grommunio-sync)
and an nginx snippet in /etc/nginx/grommunio.d/. Enable the instance
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
php_admin_value[open_basedir]=/usr/share/grommunio-sync:/etc/grommunio-sync:/var/log/grommunio-sync:/etc/gromox:/usr/share/php-mapi:/usr/share/php:/run/gromox
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

%files
%{_datadir}/%{name}
%dir %{_sysconfdir}/%{name}
%config(noreplace) %{_sysconfdir}/%{name}/config.php
%{_sbindir}/grommunio-sync-top
%config(noreplace) %{_sysconfdir}/logrotate.d/%{name}
%config(noreplace) %{_sysconfdir}/php-fpm-instances.d/grommunio-sync.conf
%config(noreplace) %{_sysconfdir}/php-fpm-instances.d/grommunio-sync.env
%config(noreplace) %{_sysconfdir}/nginx/grommunio.d/sync.conf
%dir %attr(0770,www,www) %{_localstatedir}/log/%{name}
