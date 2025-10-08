# 📝 TODO - Migration Système de Logging

## ✅ Fait

1. ✅ Créé `app/logger.py` - Module de logging complet
2. ✅ Intégré logger dans imports de `app/main.py`
3. ✅ Logs de démarrage application avec configuration
4. ✅ Logs route `/streams/records` (accès fichiers)
5. ✅ Logs début de route `/api/start`
6. ✅ Documentation complète dans `LOGGING_IMPROVEMENTS.md`

## 🔄 En Cours - app/main.py

### Route `/api/start` (lignes 353-450)
- [x] Section démarrage
- [x] Validation paramètres
- [ ] Résolution source type (ligne 375-379)
- [ ] Résolution Chaturbate (ligne 381-405)
- [ ] Inférence person depuis URL (ligne 411-420)
- [ ] Slugification (ligne 422-424)
- [ ] Démarrage session FFmpeg (ligne 426-436)
- [ ] Réponse finale (ligne 438-450)

### Autres routes à migrer:
- [ ] `/api/status` (ligne 453-455)
- [ ] `/api/stop/{session_id}` (ligne 458-463)
- [ ] `/api/model/{username}/status` (ligne 466+)
- [ ] `/api/models` - GET (liste)
- [ ] `/api/models` - POST (ajout)
- [ ] `/api/models/{username}` - PUT (modification)
- [ ] `/api/models/{username}` - DELETE (suppression)
- [ ] `/api/recordings/{username}` - GET (liste)
- [ ] `/api/recordings/{username}/{filename}` - DELETE
- [ ] `/api/git/status` - GET
- [ ] `/api/git/update` - POST

## ⏳ À Faire - app/ffmpeg_runner.py

### FFmpegSession
- [ ] `__init__` - Log création session
- [ ] `is_running` - Log état
- [ ] `record_path_today` - Log chemin
- [ ] `_writer_loop` - Logs écriture + rotation

### FFmpegManager
- [ ] `__init__` - Log initialisation
- [ ] `start_session` - **PRIORITÉ** Logs détaillés démarrage
  - Vérification session existante
  - Création répertoires
  - Construction commande FFmpeg
  - Démarrage processus
  - Thread writer
- [ ] `stop_session` - Logs arrêt
  - Arrêt processus
  - Attente thread
  - Nettoyage
- [ ] `list_status` - Logs listing sessions

## ⏳ À Faire - app/resolvers/chaturbate.py

### resolve_m3u8(username)
- [ ] Log début résolution
- [ ] Log requête API Chaturbate
- [ ] Log parsing réponse
- [ ] Log extraction URL M3U8
- [ ] Log erreurs détaillées
- [ ] Log succès avec détails

## ⏳ À Faire - Background Tasks

### auto_record_task() 
- [ ] Log démarrage task
- [ ] Log cycle vérification
- [ ] Log modèles chargés
- [ ] Log vérification par modèle
  - autoRecord activé/désactivé
  - Déjà en enregistrement
  - Appel API Chaturbate
  - Modèle online/offline
  - Démarrage enregistrement
- [ ] Log erreurs par modèle
- [ ] Log erreurs task

### cleanup_old_recordings_task()
- [ ] Log démarrage task
- [ ] Log cycle nettoyage
- [ ] Log par modèle
  - Rétention configurée
  - Fichiers à supprimer
  - Suppressions effectuées
  - Erreurs suppression
- [ ] Log statistiques (total supprimé, espace libéré)
- [ ] Log erreurs task

## 📊 Statistiques

### Fichiers Python à Migrer:
- `app/main.py` : **32 print()** à remplacer
- `app/ffmpeg_runner.py` : **19 print()** à remplacer  
- `app/resolvers/chaturbate.py` : **31 print()** à remplacer

**Total : 82 print() à migrer vers logger**

## 🎯 Priorités

### Priorité 1 (CRITIQUE) :
1. `app/ffmpeg_runner.py` - start_session / stop_session
2. `app/main.py` - route /api/start complète
3. `app/resolvers/chaturbate.py` - resolve_m3u8

### Priorité 2 (IMPORTANTE) :
4. Background task auto_record
5. Routes API modèles (CRUD)
6. Routes API enregistrements

### Priorité 3 (UTILE) :
7. Background task cleanup
8. Routes Git
9. Routes diverses (status, stop)

## 🔧 Approche Recommandée

### Phase 1 : Core Functionality (Priorité 1)
```bash
1. Modifier app/ffmpeg_runner.py (2h)
   - start_session avec tous les détails
   - stop_session avec durée
   - Logs erreurs FFmpeg
   
2. Compléter app/main.py /api/start (1h)
   - Tous les print() -> logger
   - Contexte sur chaque étape
   
3. Modifier app/resolvers/chaturbate.py (1h)
   - Requêtes API tracées
   - Réponses loggées
   - Erreurs détaillées
```

### Phase 2 : API Routes (Priorité 2)
```bash
4. Routes modèles (1h)
   - model_operation() pour chaque CRUD
   - Erreurs détaillées
   
5. Background auto-record (1h)
   - background_task() pour chaque cycle
   - Détails par modèle
```

### Phase 3 : Finition (Priorité 3)
```bash
6. Cleanup task (30min)
7. Routes Git (30min)
8. Routes diverses (30min)
```

**Temps Total Estimé : 7-8 heures**

## 📝 Template de Migration

### Avant :
```python
print(f"✅ Session créée: {session_id}")
```

### Après :
```python
logger.success("Session créée", session_id=session_id, person=person)
```

### Erreurs Avant :
```python
print(f"❌ ERROR: {error}")
traceback.print_exc()
```

### Erreurs Après :
```python
logger.error("Description claire", exc_info=True, context1=value1)
```

## 🚀 Prochaine Étape

**Commencer par app/ffmpeg_runner.py car c'est le coeur du système**

Le FFmpegManager doit avoir des logs parfaits pour:
- Debugging des problèmes d'enregistrement
- Traçabilité des sessions
- Monitoring en temps réel
- Alertes sur erreurs

---

*Dernière mise à jour : 2025-10-08*
