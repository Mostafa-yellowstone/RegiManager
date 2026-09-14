import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import { API_BASE_URL, ApiError, getStoredToken } from '@/lib/api';

export type DownloadedDocument = {
  uri: string;
  mimeType: string;
  isImage: boolean;
  isPdf: boolean;
  title: string;
  ext: string;
};

function guessExtension(contentType: string | null, fallbackName: string): string {
  const lower = (contentType || '').toLowerCase();
  if (lower.includes('pdf')) return 'pdf';
  if (lower.includes('png')) return 'png';
  if (lower.includes('jpeg') || lower.includes('jpg')) return 'jpg';
  if (lower.includes('webp')) return 'webp';
  if (lower.includes('gif')) return 'gif';
  const fromName = fallbackName.split('.').pop();
  if (fromName && fromName.length <= 5) return fromName.toLowerCase();
  return 'bin';
}

function mimeForExt(ext: string): string {
  switch (ext) {
    case 'pdf':
      return 'application/pdf';
    case 'png':
      return 'image/png';
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'webp':
      return 'image/webp';
    case 'gif':
      return 'image/gif';
    default:
      return 'application/octet-stream';
  }
}

/** Authenticated remote URL for a client-wallet document file. */
export function clientDocumentUrl(kind: string, id: number | string): string {
  return `${API_BASE_URL}/api/client/documents/${kind}/${id}/file/`;
}

/**
 * Download an authenticated document into the app cache for in-app preview.
 */
export async function downloadClientDocument(
  kind: string,
  id: number | string,
  title = 'document',
): Promise<DownloadedDocument> {
  const token = await getStoredToken();
  if (!token) {
    throw new ApiError(401, 'Not signed in.');
  }

  const cacheDir = FileSystem.cacheDirectory;
  if (!cacheDir) {
    throw new ApiError(500, 'File cache is unavailable on this device.');
  }

  const url = clientDocumentUrl(kind, id);
  const safeTitle = (title || 'document').replace(/[^\w.-]+/g, '_').slice(0, 60);
  const target = `${cacheDir}wallet_${kind}_${id}_${safeTitle}`;

  const result = await FileSystem.downloadAsync(url, target, {
    headers: {
      Authorization: `Token ${token}`,
      Accept: '*/*',
    },
  });

  if (result.status < 200 || result.status >= 300) {
    throw new ApiError(result.status, 'Could not download document.');
  }

  const contentType =
    result.headers?.['Content-Type'] || result.headers?.['content-type'] || null;
  const ext = guessExtension(contentType, safeTitle);
  const finalPath = result.uri.match(/\.\w{2,5}$/) ? result.uri : `${result.uri}.${ext}`;
  if (finalPath !== result.uri) {
    await FileSystem.moveAsync({ from: result.uri, to: finalPath });
  }

  const mimeType = contentType?.split(';')[0]?.trim() || mimeForExt(ext);
  const isImage = mimeType.startsWith('image/') || ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext);
  const isPdf = mimeType.includes('pdf') || ext === 'pdf';

  return {
    uri: finalPath,
    mimeType,
    isImage,
    isPdf,
    title: title || 'Document',
    ext,
  };
}

/**
 * Download + open the system share sheet (fallback only).
 */
export async function openClientDocument(kind: string, id: number | string, title = 'document') {
  const file = await downloadClientDocument(kind, id, title);
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, {
      dialogTitle: title || 'Open document',
      mimeType: file.mimeType,
    });
  } else {
    throw new ApiError(500, 'Sharing is not available on this device.');
  }
}
