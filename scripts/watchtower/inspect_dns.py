#!/usr/bin/env python3
"""Read-only DNS ownership and failed-helper evidence on Watchtower."""
import json
from pathlib import Path
import socket
import subprocess


def report(name, command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=25)
        print(json.dumps({'check': name, 'returncode': result.returncode,
                          'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}), flush=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'check': name, 'error_type': type(error).__name__}), flush=True)


def main():
    if socket.gethostname().split('.')[0] != 'watchtower':
        raise RuntimeError('Inspection requires Watchtower')
    for unit in ['unbound-resolvconf.service', 'unbound.service',
                 'systemd-resolved.service', 'AdGuardHome.service']:
        report(unit, ['systemctl', 'show', unit, '--no-pager',
            '--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,FragmentPath,DropInPaths'])
    report('helper_unit', ['systemctl', 'cat', 'unbound-resolvconf.service'])
    report('helper_journal', ['journalctl', '-u', 'unbound-resolvconf.service',
        '-b', '--no-pager', '-n', '50', '-o', 'short-iso'])
    report('resolver_status', ['resolvectl', 'status', '--no-pager'])
    report('resolver_packages', ['dpkg-query', '-W', '-f=${binary:Package} ${Version}\n',
        'unbound', 'resolvconf', 'openresolv', 'systemd-resolved'])
    resolver = Path('/etc/resolv.conf')
    print(json.dumps({'resolver_file': {'target': str(resolver.resolve()),
        'content': resolver.read_text() if resolver.exists() else None}}), flush=True)
    # Package helper scripts/configuration contain resolver plumbing, not AdGuard credentials.
    for filename in ['/etc/default/unbound', '/usr/lib/unbound/package-helper']:
        path = Path(filename)
        print(json.dumps({'file': filename, 'content': path.read_text() if path.is_file() else None}), flush=True)
    report('unbound_config_valid', ['unbound-checkconf'])
    for option in ['interface', 'port', 'do-ip4', 'do-ip6']:
        report('unbound_' + option, ['unbound-checkconf', '-o', option])
    report('dns_listeners', ['ss', '-lntup', '( sport = :53 or sport = :5335 )'])
    for name, address, port in [('recursive', '127.0.0.1', '5335'),
                                ('adguard', '192.168.30.11', '53')]:
        report(name + '_dns', ['dig', '@' + address, '-p', port, 'example.com', 'A',
                              '+time=3', '+tries=1', '+noall', '+comments', '+answer'])
    report('host_dns', ['getent', 'ahostsv4', 'example.com'])
    report('failed_units', ['systemctl', '--failed', '--no-pager', '--plain', '--no-legend'])


if __name__ == '__main__':
    main()
