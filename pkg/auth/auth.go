package auth

import (
	"sync"

	"github.com/prashah/batwa/pkg/models"
)

// Simple in-memory session and user storage
// In production, use Redis or a database
var (
	Sessions = make(map[string]*models.Session)
	Users    = map[string]string{
		"admin": "admin123", // username: password
	}
	sessionMutex sync.RWMutex
)

// CheckAuth checks if a session ID is valid
func CheckAuth(sessionID string) bool {
	if sessionID == "" {
		return false
	}
	sessionMutex.RLock()
	defer sessionMutex.RUnlock()
	_, exists := Sessions[sessionID]
	return exists
}

// GetSession gets a session by ID
func GetSession(sessionID string) (*models.Session, bool) {
	sessionMutex.RLock()
	defer sessionMutex.RUnlock()
	session, exists := Sessions[sessionID]
	return session, exists
}

// SetSession sets a session
func SetSession(sessionID string, session *models.Session) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	Sessions[sessionID] = session
}

// DeleteSession deletes a session
func DeleteSession(sessionID string) {
	sessionMutex.Lock()
	defer sessionMutex.Unlock()
	delete(Sessions, sessionID)
}
