import { API_BASE_URL } from '@/lib/api';
import { Linking } from 'react-native';

export function crmHomeUrl() {
  return `${API_BASE_URL}/dashboard/`;
}

export function crmClientsUrl() {
  return `${API_BASE_URL}/dashboard/clients/`;
}

export function crmClientUrl(clientId: string | number) {
  return `${API_BASE_URL}/dashboard/clients/${clientId}/`;
}

export function crmSpacesUrl() {
  return `${API_BASE_URL}/dashboard/spaces/`;
}

export function crmFinanceUrl() {
  return `${API_BASE_URL}/dashboard/finance/`;
}

export async function openCrmUrl(url: string): Promise<boolean> {
  try {
    const can = await Linking.canOpenURL(url);
    if (!can) return false;
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}
