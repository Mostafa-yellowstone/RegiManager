import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import { API_BASE_URL, ApiError, getStoredToken } from '@/lib/api';

export type DownloadedDocument = {
  uri: string;
  mimeType: string;
  isImage: boolean;
  isPdf: boolean;
  title: string;
  ext: string;
  base64?: string;
};

const IMAGE_EXTS = new Set([
  'png',
  'jpg',
  'jpeg',
  'webp',
  'gif',
  'bmp',
  'heic',
  'heif',
  'tif',
  'tiff',
  'jfif',
]);

function extFromName(name: string | null | undefined): string | null {
  if (!name) return null;
  const clean = name.split('?')[0].split('#')[0];
  const parts = clean.split('.');
  if (parts.length < 2) return null;
  const ext = parts.pop()!.toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!ext || ext.length > 5) return null;
  return ext;
}

function guessExtensionFromMime(contentType: string | null): string | null {
  const lower = (contentType || '').toLowerCase();
  if (!lower) return null;
  if (lower.includes('pdf')) return 'pdf';
  if (lower.includes('png')) return 'png';
  if (lower.includes('jpeg') || lower.includes('jpg')) return 'jpg';
  if (lower.includes('webp')) return 'webp';
  if (lower.includes('gif')) return 'gif';
  if (lower.includes('bmp')) return 'bmp';
  if (lower.includes('heic')) return 'heic';
  if (lower.includes('heif')) return 'heif';
  if (lower.includes('tiff')) return 'tiff';
  if (lower.startsWith('image/')) {
    const sub = lower.split('/')[1]?.split(';')[0]?.trim();
    if (sub && sub.length <= 5) return sub === 'jpeg' ? 'jpg' : sub;
  }
  return null;
}

function parseContentDispositionFilename(header: string | null | undefined): string | null {
  if (!header) return null;
  const utf = header.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf?.[1]) {
    try {
      return decodeURIComponent(utf[1].trim().replace(/^"|"$/g, ''));
    } catch {
      return utf[1].trim().replace(/^"|"$/g, '');
    }
  }
  const plain = header.match(/filename\s*=\s*"([^"]+)"/i) || header.match(/filename\s*=\s*([^;]+)/i);
  return plain?.[1]?.trim().replace(/^"|"$/g, '') || null;
}

function mimeForExt(ext: string): string {
  switch (ext) {
    case 'pdf':
      return 'application/pdf';
    case 'png':
      return 'image/png';
    case 'jpg':
    case 'jpeg':
    case 'jfif':
      return 'image/jpeg';
    case 'webp':
      return 'image/webp';
    case 'gif':
      return 'image/gif';
    case 'bmp':
      return 'image/bmp';
    case 'heic':
      return 'image/heic';
    case 'heif':
      return 'image/heif';
    case 'tif':
    case 'tiff':
      return 'image/tiff';
    default:
      return 'application/octet-stream';
  }
}

/** Sniff magic bytes via base64 prefix (avoids binary string APIs). */
async function sniffExtension(uri: string): Promise<string | null> {
  try {
    const head = await FileSystem.readAsStringAsync(uri, {
      encoding: FileSystem.EncodingType.Base64,
      length: 24,
      position: 0,
    });
    if (head.startsWith('JVBERi')) return 'pdf'; // %PDF
    if (head.startsWith('iVBORw0')) return 'png';
    if (head.startsWith('/9j/')) return 'jpg';
    if (head.startsWith('R0lGOD')) return 'gif';
    if (head.startsWith('Qk')) return 'bmp';
    // RIFF....WEBP
    if (head.startsWith('UklGR') && head.includes('V0VC')) return 'webp';
  } catch {
    // ignore
  }
  return null;
}

/** Authenticated remote URL for a client-wallet document file. */
export function clientDocumentUrl(kind: string, id: number | string): string {
  return `${API_BASE_URL}/api/client/documents/${kind}/${id}/file/`;
}

export function isPreviewableImage(ext: string, mimeType: string): boolean {
  const e = (ext || '').toLowerCase();
  if (IMAGE_EXTS.has(e)) {
    // HEIC/HEIF often fails on Android Image — still mark as image for iOS.
    if ((e === 'heic' || e === 'heif') && Platform.OS === 'android') return false;
    return true;
  }
  return mimeType.toLowerCase().startsWith('image/');
}

/**
 * Download an authenticated document into the app cache for in-app preview.
 */
export async function downloadClientDocument(
  kind: string,
  id: number | string,
  title = 'document',
  options?: { fileNameHint?: string | null },
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

  const headers = result.headers || {};
  const contentType =
    headers['Content-Type'] ||
    headers['content-type'] ||
    headers['CONTENT-TYPE'] ||
    null;
  const disposition =
    headers['Content-Disposition'] ||
    headers['content-disposition'] ||
    headers['CONTENT-DISPOSITION'] ||
    null;
  const xFileName =
    headers['X-File-Name'] || headers['x-file-name'] || headers['X-FILE-NAME'] || null;
  const dispositionName = parseContentDispositionFilename(disposition) || xFileName;

  let ext =
    guessExtensionFromMime(contentType) ||
    extFromName(dispositionName) ||
    extFromName(options?.fileNameHint || null) ||
    extFromName(safeTitle) ||
    (await sniffExtension(result.uri)) ||
    'bin';

  // Prefer sniff when mime was generic.
  if (ext === 'bin' || (contentType || '').includes('octet-stream')) {
    ext = (await sniffExtension(result.uri)) || ext;
  }

  const finalPath = result.uri.match(/\.\w{2,5}$/)
    ? result.uri
    : `${result.uri}.${ext}`;
  if (finalPath !== result.uri) {
    try {
      await FileSystem.moveAsync({ from: result.uri, to: finalPath });
    } catch {
      // keep original path if move fails
    }
  }

  const uri = finalPath !== result.uri && (await FileSystem.getInfoAsync(finalPath)).exists
    ? finalPath
    : result.uri;

  // Re-sniff after move if still unknown.
  if (ext === 'bin') {
    ext = (await sniffExtension(uri)) || ext;
  }

  const mimeType = (contentType || '').split(';')[0]?.trim() || mimeForExt(ext);
  const isPdf = mimeType.includes('pdf') || ext === 'pdf';
  const isImage = !isPdf && isPreviewableImage(ext, mimeType);

  let base64: string | undefined;
  if (isPdf) {
    try {
      base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      });
    } catch {
      base64 = undefined;
    }
  }

  return {
    uri,
    mimeType,
    isImage,
    isPdf,
    title: title || 'Document',
    ext,
    base64,
  };
}

/** Open with the OS share / viewer sheet (fallback for unsupported previews). */
export async function openClientDocument(
  kind: string,
  id: number | string,
  title = 'document',
  options?: { fileNameHint?: string | null },
) {
  const file = await downloadClientDocument(kind, id, title, options);
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(file.uri, {
      dialogTitle: title || 'Open document',
      mimeType: file.mimeType,
      UTI: file.isPdf ? 'com.adobe.pdf' : undefined,
    });
  } else {
    throw new ApiError(500, 'Sharing is not available on this device.');
  }
  return file;
}

export async function shareDownloadedDocument(file: DownloadedDocument) {
  if (!(await Sharing.isAvailableAsync())) {
    throw new ApiError(500, 'Sharing is not available on this device.');
  }
  await Sharing.shareAsync(file.uri, {
    dialogTitle: file.title || 'Open document',
    mimeType: file.mimeType,
    UTI: file.isPdf ? 'com.adobe.pdf' : undefined,
  });
}
