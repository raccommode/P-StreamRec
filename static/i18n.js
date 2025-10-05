// ============================================
// Système de traduction i18n
// ============================================

const translations = {
  fr: {
    // Header
    appTitle: "P-StreamRec",
    version: "Version",
    
    // Page d'accueil
    myModels: "Mes Modèles",
    addModel: "Ajouter un modèle",
    noModels: "Aucun modèle enregistré",
    noModelsDesc: "Ajoutez vos premiers modèles pour commencer à enregistrer leurs streams automatiquement",
    addFirstModel: "Ajouter un modèle",
    
    // Modal ajout
    addNewModel: "Ajouter un nouveau modèle",
    enterUrl: "Entrez l'URL du modèle ou son username",
    urlPlaceholder: "https://chaturbate.com/username ou username",
    cancel: "Annuler",
    add: "Ajouter",
    
    // Status
    recording: "En enregistrement",
    online: "En ligne",
    offline: "Hors ligne",
    viewers: "spectateurs",
    
    // Rediffusions
    recordings: "rediffusion",
    recordingsPlural: "rediffusions",
    lastRecording: "Dernier",
    
    // Notifications
    modelAdded: "ajouté avec succès!",
    modelExists: "Ce modèle est déjà dans la liste",
    invalidUrl: "URL invalide",
    connectionError: "Erreur de connexion",
    
    // Page modèle
    live: "Live",
    replays: "Rediffusions",
    noStream: "Aucun stream en cours",
    quality: "Qualité",
    best: "Meilleure",
    auto: "Auto",
    deleteModel: "Supprimer le modèle",
    deleteConfirm: "Voulez-vous vraiment supprimer",
    deleteConfirmText: "de votre liste ?",
    modelDeleted: "Modèle supprimé",
    
    noRecordings: "Aucune rediffusion",
    noRecordingsDesc: "Les enregistrements apparaîtront ici une fois que le modèle aura été en ligne",
    
    // Vidéo
    loadingReplay: "Chargement de la rediffusion...",
    resumeAt: "Reprise à",
    clickToPlay: "Cliquez sur ▶️ pour lancer la lecture",
    recordingInProgress: "Enregistrement en cours ! Regardez le live au lieu de la rediffusion.",
    playStarted: "Lecture démarrée (cliquez 🔊 pour activer le son)",
    
    // Suppression enregistrement
    deleteRecording: "Supprimer",
    deleteRecordingConfirm: "Supprimer",
    deleteRecordingText: "?\n\nCette action est irréversible.",
    recordingDeleted: "Enregistrement supprimé",
    cannotDeleteActive: "Impossible de supprimer l'enregistrement en cours.",
    
    // Erreurs
    error: "Erreur",
    errorOccurred: "Une erreur s'est produite",
    retry: "Réessayer"
  },
  
  en: {
    // Header
    appTitle: "P-StreamRec",
    version: "Version",
    
    // Homepage
    myModels: "My Models",
    addModel: "Add Model",
    noModels: "No models saved",
    noModelsDesc: "Add your first models to start recording their streams automatically",
    addFirstModel: "Add a model",
    
    // Add modal
    addNewModel: "Add New Model",
    enterUrl: "Enter model URL or username",
    urlPlaceholder: "https://chaturbate.com/username or username",
    cancel: "Cancel",
    add: "Add",
    
    // Status
    recording: "Recording",
    online: "Online",
    offline: "Offline",
    viewers: "viewers",
    
    // Recordings
    recordings: "recording",
    recordingsPlural: "recordings",
    lastRecording: "Last",
    
    // Notifications
    modelAdded: "added successfully!",
    modelExists: "This model is already in the list",
    invalidUrl: "Invalid URL",
    connectionError: "Connection error",
    
    // Model page
    live: "Live",
    replays: "Replays",
    noStream: "No stream available",
    quality: "Quality",
    best: "Best",
    auto: "Auto",
    deleteModel: "Delete Model",
    deleteConfirm: "Do you really want to remove",
    deleteConfirmText: "from your list?",
    modelDeleted: "Model deleted",
    
    noRecordings: "No recordings",
    noRecordingsDesc: "Recordings will appear here once the model has been online",
    
    // Video
    loadingReplay: "Loading replay...",
    resumeAt: "Resume at",
    clickToPlay: "Click ▶️ to start playback",
    recordingInProgress: "Recording in progress! Watch the live stream instead.",
    playStarted: "Playback started (click 🔊 to enable sound)",
    
    // Delete recording
    deleteRecording: "Delete",
    deleteRecordingConfirm: "Delete",
    deleteRecordingText: "?\n\nThis action is irreversible.",
    recordingDeleted: "Recording deleted",
    cannotDeleteActive: "Cannot delete recording in progress.",
    
    // Errors
    error: "Error",
    errorOccurred: "An error occurred",
    retry: "Retry"
  }
};

// Langue par défaut
let currentLang = localStorage.getItem('p-streamrec-lang') || 'fr';

// Récupérer une traduction
function t(key) {
  return translations[currentLang]?.[key] || translations['fr'][key] || key;
}

// Changer de langue
function setLanguage(lang) {
  if (!translations[lang]) return;
  currentLang = lang;
  localStorage.setItem('p-streamrec-lang', lang);
  
  // Recharger la page pour appliquer les traductions
  window.location.reload();
}

// Obtenir la langue actuelle
function getCurrentLanguage() {
  return currentLang;
}

// Initialiser les boutons de langue
function initLanguageSelector() {
  const langButtons = document.querySelectorAll('[data-lang]');
  langButtons.forEach(btn => {
    if (btn.dataset.lang === currentLang) {
      btn.classList.add('active');
    }
    btn.addEventListener('click', () => {
      setLanguage(btn.dataset.lang);
    });
  });
}

// Traduire automatiquement les éléments avec data-i18n
function translatePage() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const translation = t(key);
    
    if (el.tagName === 'INPUT' && el.placeholder !== undefined) {
      el.placeholder = translation;
    } else {
      el.textContent = translation;
    }
  });
}

// Initialiser au chargement
document.addEventListener('DOMContentLoaded', () => {
  initLanguageSelector();
  translatePage();
});
