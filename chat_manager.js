// Chat Browser - Read-only viewer for hermes-agent chat history
// Loads sessions from hermes state.db via server API

const API_BASE = window.location.origin;

// State
let currentSessionId = null;
let sessions = [];
let isLoading = false;

// DOM elements
let chatHistory = null;
let chatList = null;
let chatTitle = null;
let chatViewerInfo = null;

// Initialize chat browser
function initChatBrowser() {
  chatHistory = document.getElementById('chatHistory');
  chatList = document.getElementById('chatList');
  chatTitle = document.getElementById('chatTitle');
  chatViewerInfo = document.getElementById('chatViewerInfo');

  if (!chatHistory || !chatList) {
    console.warn('ChatBrowser: Required elements not found');
    return;
  }

  // Load sessions on init
  loadSessions();

  // Set up event listeners
  setupEventListeners();

  console.log('ChatBrowser: Initialized');
}

// Load sessions from API
async function loadSessions() {
  if (isLoading) return;
  isLoading = true;

  try {
    const response = await fetch(API_BASE + '/api/sessions?limit=50');
    if (!response.ok) {
      throw new Error('Failed to load sessions');
    }

    sessions = await response.json();
    renderSessionList();
    console.log('ChatBrowser: Loaded ' + sessions.length + ' sessions');
  } catch (error) {
    console.error('ChatBrowser: Failed to load sessions', error);
    renderError('Failed to load chat history. Is hermes-agent running?');
  } finally {
    isLoading = false;
  }
}

// Render session list in sidebar
function renderSessionList() {
  if (!chatList) return;

  if (sessions.length === 0) {
    chatList.innerHTML = '<div class="chat-list-empty">No chat history found</div>';
    return;
  }

  chatList.innerHTML = sessions.map(session => {
    const isActive = session.id === currentSessionId;
    const title = session.title || 'Untitled Chat';
    const timeStr = formatTimestamp(session.last_active || session.started_at);
    const preview = session.preview || '';

    return `<div class="chat-list-item ${isActive ? 'active' : ''}" data-session-id="${session.id}">
      <div class="chat-list-item-content">
        <div class="chat-list-item-name">${escapeHtml(title)}</div>
        <div class="chat-list-item-meta">
          <span class="chat-list-item-time">${timeStr}</span>
        </div>
        ${preview ? `<div class="chat-list-item-preview">${escapeHtml(preview)}</div>` : ''}
      </div>
    </div>`;
  }).join('');

  // Add click handlers
  chatList.querySelectorAll('.chat-list-item').forEach(item => {
    item.addEventListener('click', () => {
      const sessionId = item.dataset.sessionId;
      loadSession(sessionId);
    });
  });
}

// Load and display a specific session
async function loadSession(sessionId) {
  if (sessionId === currentSessionId) return;

  currentSessionId = sessionId;
  renderSessionList(); // Update active state

  // Show copy button
  const copyBtn = document.getElementById('copySessionIdBtn');
  if (copyBtn) copyBtn.style.display = 'block';

  // Show loading state
  chatHistory.innerHTML = '<div class="chat-loading">Loading messages...</div>';
  chatViewerInfo.style.display = 'none';

  try {
    const response = await fetch(API_BASE + `/api/sessions/${sessionId}/messages`);
    if (!response.ok) {
      throw new Error('Failed to load messages');
    }

    const messages = await response.json();
    renderMessages(messages);

    // Update title
    const session = sessions.find(s => s.id === sessionId);
    chatTitle.textContent = session?.title || 'Untitled Chat';

    console.log('ChatBrowser: Loaded ' + messages.length + ' messages for session ' + sessionId);
  } catch (error) {
    console.error('ChatBrowser: Failed to load session', error);
    chatHistory.innerHTML = '<div class="chat-error">Failed to load messages</div>';
  }
}

// Render messages in chat history
function renderMessages(messages) {
  if (!chatHistory) return;

  if (messages.length === 0) {
    chatHistory.innerHTML = '<div class="chat-empty">No messages in this conversation</div>';
    return;
  }

  chatHistory.innerHTML = messages.map(msg => {
    const isUser = msg.role === 'user';
    const timeStr = formatTimestamp(msg.timestamp);

    return `<div class="chat-message ${isUser ? 'user-message' : 'assistant-message'}">
      <div class="message-content">${escapeHtml(msg.content)}</div>
      <div class="message-time">${timeStr}</div>
    </div>`;
  }).join('');

  // Scroll to top (most recent messages at top)
  chatHistory.scrollTop = 0;
}

// Render error message
function renderError(message) {
  if (chatList) {
    chatList.innerHTML = `<div class="chat-list-error">${escapeHtml(message)}</div>`;
  }
}

// Format timestamp for display
function formatTimestamp(timestamp) {
  if (!timestamp) return '';

  let date;
  if (typeof timestamp === 'number') {
    // Unix timestamp (seconds)
    date = new Date(timestamp * 1000);
  } else {
    // ISO string
    date = new Date(timestamp);
  }

  const now = new Date();
  const diff = now - date;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return 'just now';
  if (minutes < 60) return minutes + (minutes === 1 ? ' min ago' : ' mins ago');
  if (hours < 24) return hours + (hours === 1 ? ' hour ago' : ' hours ago');
  if (days < 7) return days + (days === 1 ? ' day ago' : ' days ago');

  return date.toLocaleDateString();
}

// Escape HTML to prevent XSS
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Setup event listeners
function setupEventListeners() {
  // Sidebar toggle
  document.addEventListener('click', (event) => {
    const actionEl = event.target.closest('[data-action]');
    if (!actionEl) return;

    const action = actionEl.dataset.action;
    if (action === 'toggle-chat-sidebar') {
      toggleChatSidebar();
    }
  });
}

// Toggle chat sidebar visibility
function toggleChatSidebar() {
  const sidebar = document.getElementById('chatSidebar');
  if (!sidebar) return;

  sidebar.classList.toggle('visible');
  const isVisible = sidebar.classList.contains('visible');
  localStorage.setItem('waifuChatSidebarVisible', isVisible.toString());
}

// Refresh sessions
function refreshSessions() {
  loadSessions();
}

// Expose to global scope
window.ChatBrowser = {
  init: initChatBrowser,
  loadSessions: loadSessions,
  loadSession: loadSession,
  refreshSessions: refreshSessions,
  toggleChatSidebar: toggleChatSidebar
};

// Expose functions for onclick handlers
window.toggleChatSidebar = toggleChatSidebar;
window.refreshSessions = refreshSessions;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initChatBrowser);
} else {
  initChatBrowser();
}