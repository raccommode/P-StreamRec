# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/).

## [2025.40.B] - 2025-10-08

### ✨ Ajouté
- **GitOps Updates** : Mises à jour one-click depuis l'interface web
- **Système de logging professionnel** : Logger centralisé avec couleurs et timestamps
- **Auto-enregistrement configurable** : Case à cocher par modèle
- **Rétention automatique** : Nettoyage programmé des anciennes rediffusions
- **Configuration qualité** : Sélection de la qualité d'enregistrement par modèle
- **Menu paramètres** : Interface centralisée pour chaque modèle
- **Middleware requêtes** : Log automatique de toutes les requêtes API
- **Structure modulaire** : Organisation app/core, app/api, app/tasks
- **Background tasks séparés** : auto_record.py et cleanup.py
- **Utilitaires centralisés** : app/core/utils.py et app/core/config.py

### 🔧 Modifié
- **app/ffmpeg_runner.py** : Migration complète vers le système de logging
- **app/resolvers/chaturbate.py** : Migration vers logger avec logs détaillés
- **app/main.py** : Middleware de logging, imports optimisés
- **Version** : Nouveau format ANNÉE.SEMAINE.LETTRE (2025.40.B)
- **README** : Documentation complète en anglais
- **.gitignore** : Ajout .DS_Store, .vscode/, .idea/, *.swp

### 🗂️ Réorganisé
- **docs/** : Documentation déplacée et organisée
  - LOGGING_IMPROVEMENTS.md
  - TODO_LOGGING.md
- **scripts/** : Scripts utilitaires déplacés
  - check_health.py
- **app/core/** : Configuration et utilitaires centralisés
- **app/tasks/** : Background tasks modulaires

### 🗑️ Supprimé
- **app/auto_recorder.py** : Fonctionnalité intégrée dans main.py
- **static/migrate.html** : Page de migration obsolète
- **.DS_Store** : Fichier système macOS

### 🐛 Corrigé
- Session FFmpeg : Logs détaillés sur toutes les opérations
- Writer loop : Logs rotation fichier jour
- Cleanup task : Logs suppressions avec taille libérée
- Resolver : Meilleure gestion des erreurs

### 📝 Documentation
- **REORGANIZATION_PLAN.md** : Plan complet de réorganisation
- **CHANGELOG.md** : Historique des versions
- **API** : Endpoints GitOps documentés
- **README** : Section GitOps Updates ajoutée

### 🎨 Performance
- Imports optimisés
- Code modulaire et maintenable
- Séparation des responsabilités
- Background tasks isolés

## [2025.40.A] - 2025-10-05

### ✨ Ajouté
- Interface simplifiée avec paramètres centralisés
- Qualité d'enregistrement configurable
- Rétention automatique des rediffusions
- Version automatiquement synchronisée
- Cache métadonnées rediffusions (30x plus rapide)
- Système de version ANNÉE.SEMAINE.LETTRE

### 🔧 Modifié
- Auto-enregistrement en arrière-plan
- Sauvegarde serveur (navigation privée OK)
- Protection enregistrement en cours

## [1.0.0] - 2025-10-04

### ✨ Version Initiale
- Enregistrement automatique Chaturbate
- Interface web moderne
- Rotation fichiers quotidienne
- Support m3u8 direct
- Docker ready
- Multilingue (FR/EN)

---

## Types de Changements

- **✨ Ajouté** : Nouvelles fonctionnalités
- **🔧 Modifié** : Changements de fonctionnalités existantes
- **🗑️ Supprimé** : Fonctionnalités supprimées
- **🐛 Corrigé** : Corrections de bugs
- **🔒 Sécurité** : Corrections de vulnérabilités
- **📝 Documentation** : Modifications de documentation
- **🎨 Performance** : Améliorations de performance
- **🗂️ Réorganisé** : Changements de structure
