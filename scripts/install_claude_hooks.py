#!/usr/bin/env python3
"""Install the local QA adapter in Claude user settings without replacing other hooks."""
import argparse
from install_codex_hooks import change


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--path', default='~/.claude/settings.json')
    args = parser.parse_args()
    change(args.path, args.action)
    print('Gardenstep QA hooks updated; existing settings and other hooks were preserved.')


if __name__ == '__main__':
    main()
