#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace CLI tool for managing Docker Compose with Jinja2 templates.

This is the main entry point that delegates to modular components in ws-src/.
"""

from ws_src.commands import main

if __name__ == "__main__":
    main()
