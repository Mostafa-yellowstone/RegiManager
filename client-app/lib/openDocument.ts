import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import { API_BASE_URL, ApiError, getStoredToken } from '@/lib/api';

function guessExtension(contentType: string | null, fallbackName: string): string {
  const lower = (contentType || '').toLowerCase();
  if (lower.includes('pdf')) return 'pdf';
  if (lower.includes('png')) return 'png';
  if (lower.includes('jpeg') || lower.includes('jpg')) return 'jpg';
  if (lower.includes('webp')) return 'webp';
  const fromName = fallbackName.split('.').pop();
  if (fromName && fromName.length <= 5) return fromName;
  return 'bin';
}

/**
 * Download an authenticated client-wallet document and open the system share/viewer sheet.
 */
export async function openClientDocument(kind: string, id: number | string, title = 'document') {
  const token = await getStoredToken();
  if (!token) {
    throw new ApiError(401, 'Not signed in.');
  }

  const cacheDir = FileSystem.cacheDirectory;
  if (!cacheDir) {
    throw new ApiError(500, 'File cache is unavailable on this device.');
  }

  const url = `${API_BASE_URL}/api/client/documents/${kind}/${id}/file/`;
  const safeTitle = (title || 'document').replace(/[^\w.-]+/g, '_').slice(0, 60);
  const target = `${cacheDir}wallet_${kind}_${id}_${Date.now()}_${safeTitle}`;

  const result = await FileSystem.downloadAsync(url, target, {
    headers: {
      Authorization: `Token ${token}`,
      Accept: '*/*',
    },
  });

  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(result.status, 'Could not download document.');
  }

  const ext = guessExtension(result.headers?.['Content-Type'] || result.headers?.['content-type'] || null, safeTitle);
  const finalPath = result.uri.includes('.') ? result.uri : `${result.uri}.${ext}`;
  if (finalPath !== result.uri) {
    await FileSystem.moveAsync({ from: result.uri, to: finalPath });
  }

  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(finalPath, {
      dialogTitle: title || 'Open document',
      mimeType:
        ext === 'pdf'
          ? 'application/pdf'
          : ext === 'png'
            ? 'image/png'
            : ext === 'jpg'
              ? 'image/jpeg'
              : undefined,
    });
  } else {
    throw new ApiError(500, 'Sharing is not available on this device.');
  }
}
