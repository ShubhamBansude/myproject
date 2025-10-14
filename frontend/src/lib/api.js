// Central API URL helper for cross-device deployments
// Reads Vite env VITE_API_BASE_URL; falls back to http://localhost:5000

const base = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL)
  ? String(import.meta.env.VITE_API_BASE_URL).replace(/\/$/, '')
  : 'http://localhost:5000';

export function apiUrl(path) {
  const cleanPath = String(path || '').trim();
  if (!cleanPath) return base;
  return cleanPath.startsWith('/') ? `${base}${cleanPath}` : `${base}/${cleanPath}`;
}

export const API_BASE_URL = base;
