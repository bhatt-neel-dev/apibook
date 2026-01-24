# .gitignore

# ============================================================================
# Python / Django
# ============================================================================

# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class
*.so

# C extensions
*.c
*.cpp
*.h

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.hypothesis/
.pytest_cache/
cover/

# Translations
*.mo
*.pot

# Django stuff
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff
instance/
.webassets-cache

# Scrapy stuff
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
.pybuilder/
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
.python-version

# pipenv
Pipfile.lock

# poetry
poetry.lock

# pdm
.pdm.toml

# PEP 582
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.env.local
.env.*.local
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# pytype static type analyzer
.pytype/

# Cython debug symbols
cython_debug/

# ============================================================================
# UV (Python Package Manager)
# ============================================================================

# UV lock file (commit this!)
# uv.lock should be committed, but exclude if you want fresh resolves
# uv.lock

# UV cache
.uv/

# ============================================================================
# Django Specific
# ============================================================================

# Static files (collected by collectstatic)
staticfiles/
static_root/
/static/admin/
/static/rest_framework/

# Media files
media/
media_root/

# Database
*.db
*.sqlite
*.sqlite3

# Django migrations (optional - some teams gitignore these)
# */migrations/*.py
# !*/migrations/__init__.py

# Django secret key
secret_key.txt

# ============================================================================
# JavaScript / Node / Frontend
# ============================================================================

# Dependencies
node_modules/
jspm_packages/

# Package manager files
package-lock.json
yarn.lock
pnpm-lock.yaml
.pnp
.pnp.js

# Testing
coverage/

# Production builds
static/dist/
static/build/
dist/
build/

# Next.js
.next/
out/

# Nuxt.js
.nuxt/
dist/

# Gatsby
.cache/
public/

# VuePress
.vuepress/dist

# Serverless
.serverless/

# FuseBox
.fusebox/

# DynamoDB Local
.dynamodb/

# TernJS
.tern-port

# Stores VSCode versions used for testing
.vscode-test

# Temporary folders
tmp/
temp/

# ============================================================================
# Frontend Build Tools
# ============================================================================

# Webpack
.webpack/

# Vite
.vite/
vite.config.js.timestamp-*
vite.config.ts.timestamp-*

# Turbopack
.turbopack/

# Parcel
.parcel-cache/

# ============================================================================
# Mintlify Docs
# ============================================================================

# Mintlify build output
docs/.mintlify/

# ============================================================================
# Docker
# ============================================================================

# Docker volumes
docker-compose.override.yml
.docker/

# ============================================================================
# Databases
# ============================================================================

# PostgreSQL
*.sql
*.dump
*.backup

# ClickHouse data
clickhouse_data/
clickhouse/

# Redis
dump.rdb
appendonly.aof

# ============================================================================
# Logs
# ============================================================================

# Application logs
logs/
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*
lerna-debug.log*
.pnpm-debug.log*

# Django logs
django.log
celery.log

# Gunicorn logs
gunicorn.log
gunicorn-access.log
gunicorn-error.log

# ============================================================================
# IDE / Editor
# ============================================================================

# VSCode
.vscode/
!.vscode/settings.json
!.vscode/tasks.json
!.vscode/launch.json
!.vscode/extensions.json
*.code-workspace

# JetBrains IDEs (PyCharm, WebStorm, IntelliJ, etc.)
.idea/
*.iml
*.iws
*.ipr
.idea_modules/

# Sublime Text
*.sublime-project
*.sublime-workspace

# Vim
[._]*.s[a-v][a-z]
[._]*.sw[a-p]
[._]s[a-rt-v][a-z]
[._]ss[a-gi-z]
[._]sw[a-p]
*.swp
*.swo
*~

# Emacs
*~
\#*\#
/.emacs.desktop
/.emacs.desktop.lock
*.elc
auto-save-list
tramp
.\#*

# Nano
*.save
*.swp

# ============================================================================
# Operating System
# ============================================================================

# macOS
.DS_Store
.AppleDouble
.LSOverride
._*
.DocumentRevisions-V100
.fseventsd
.Spotlight-V100
.TemporaryItems
.Trashes
.VolumeIcon.icns
.com.apple.timemachine.donotpresent
.AppleDB
.AppleDesktop
Network Trash Folder
Temporary Items
.apdisk

# Windows
Thumbs.db
Thumbs.db:encryptable
ehthumbs.db
ehthumbs_vista.db
*.stackdump
[Dd]esktop.ini
$RECYCLE.BIN/
*.cab
*.msi
*.msix
*.msm
*.msp
*.lnk

# Linux
*~
.directory
.Trash-*
.nfs*

# ============================================================================
# Cloud & Deployment
# ============================================================================

# AWS
.aws/
*.pem

# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
crash.log
crash.*.log
override.tf
override.tf.json
*_override.tf
*_override.tf.json
.terraformrc
terraform.rc

# Kubernetes
kubeconfig
*.kubeconfig

# ============================================================================
# CI/CD
# ============================================================================

# GitHub Actions (keep workflows but ignore outputs)
# .github/workflows/  # Don't ignore workflows themselves

# GitLab CI
.gitlab-ci-local/

# CircleCI
.circleci/config.local.yml

# ============================================================================
# Security & Secrets
# ============================================================================

# Environment variables
.env
.env.local
.env.development.local
.env.test.local
.env.production.local
.env.staging

# Secrets
secrets/
*.key
*.pem
*.p12
*.pfx
*.cer
*.crt
*.der
.secrets/

# SSL certificates
*.crt
*.key
*.pem
ssl/
certs/

# Auth0
auth0-config.json

# API keys
api-keys.txt
.api-keys

# ============================================================================
# Testing
# ============================================================================

# pytest
.pytest_cache/
.coverage
.coverage.*
htmlcov/

# Jest
coverage/

# Playwright
playwright-report/
playwright/.cache/
test-results/

# Cypress
cypress/videos/
cypress/screenshots/

# ============================================================================
# Build Artifacts
# ============================================================================

# Python wheels
*.whl

# Compiled source
*.com
*.class
*.dll
*.exe
*.o
*.so

# Archives
*.7z
*.dmg
*.gz
*.iso
*.jar
*.rar
*.tar
*.zip

# ============================================================================
# Monitoring & Analytics
# ============================================================================

# Sentry
.sentryclirc

# New Relic
newrelic.ini

# ============================================================================
# Miscellaneous
# ============================================================================

# Backup files
*.bak
*.backup
*.old
*.orig

# Temporary files
*.tmp
*.temp

# Lock files (optional - some teams commit these)
# package-lock.json
# yarn.lock
# pnpm-lock.yaml

# macOS specific Python
.Python

# Profiling data
*.prof

# Benchmarking
.benchmarks/

# Scraped data
scraped_data/

# Generated files
generated/

# Cache directories
.cache/
.parcel-cache/

# Storybook
storybook-static/

# ============================================================================
# Project Specific
# ============================================================================

# Local development overrides
docker-compose.override.yml
docker-compose.local.yml

# Data directories
data/
uploads/
downloads/

# Seed data (if you have large seed files)
# seed_data/

# Local scripts (for personal use)
local_scripts/
personal/

# Documentation build output
docs/_build/
docs/site/

# API documentation
api-docs/generated/

# Screenshots/demos (if large)
# screenshots/
# demos/

# ============================================================================
# Keep These Files (Explicit Exceptions)
# ============================================================================

# Keep empty directories
!.gitkeep

# Keep GitHub workflows
!.github/workflows/**

# Keep Docker configs
!Dockerfile*
!docker-compose*.yml
!.dockerignore

# Keep CI configs
!.gitlab-ci.yml
!.circleci/config.yml

# Keep documentation configs
!docs/mint.json
!mkdocs.yml

# Keep linter configs
!.eslintrc*
!.prettierrc*
!.pylintrc
!.flake8
!pyproject.toml

# Keep editor configs that should be shared
!.editorconfig

# Keep example files
!.env.example
!docker-compose.example.yml

# ============================================================================
# UV Lock File Decision
# ============================================================================

# IMPORTANT: Decide whether to commit uv.lock
#
# Option 1: COMMIT uv.lock (RECOMMENDED for applications)
# - Ensures reproducible builds
# - Everyone gets exact same versions
# - Better for deployment
# Uncomment the line below to EXCLUDE uv.lock:
# uv.lock

# Option 2: DON'T COMMIT uv.lock (for libraries)
# - Allows users to get latest compatible versions
# - Better for libraries/packages
# Keep uv.lock in git (default - do nothing)

# ============================================================================
# End of .gitignore
# ============================================================================