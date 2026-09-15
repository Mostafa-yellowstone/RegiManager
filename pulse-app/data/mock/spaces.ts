import type { Service, Space, User } from '@/types/models';

export const MOCK_OWNER: User = {
  id: 'user-owner-1',
  name: 'Alex Rivera',
  email: 'alex@regimanager.com',
  role: 'owner',
  space_ids: ['space-midtown', 'space-brooklyn', 'space-queens'],
};

export const MOCK_SPACES: Space[] = [
  {
    id: 'space-midtown',
    name: 'Midtown Hub',
    location: 'Manhattan, NY',
    timezone: 'America/New_York',
    operational_hours: { open: '08:00', close: '20:00' },
  },
  {
    id: 'space-brooklyn',
    name: 'Brooklyn Studio',
    location: 'Brooklyn, NY',
    timezone: 'America/New_York',
    operational_hours: { open: '09:00', close: '19:00' },
  },
  {
    id: 'space-queens',
    name: 'Queens Detail',
    location: 'Queens, NY',
    timezone: 'America/New_York',
    operational_hours: { open: '08:30', close: '18:30' },
  },
];

export const MOCK_SERVICES: Service[] = [
  {
    id: 'svc-haircut',
    space_id: 'space-midtown',
    name: 'Signature Haircut',
    cost: 18,
    price: 65,
    category: 'Grooming',
    duration_minutes: 45,
  },
  {
    id: 'svc-massage',
    space_id: 'space-brooklyn',
    name: 'Deep Tissue Massage',
    cost: 40,
    price: 120,
    category: 'Wellness',
    duration_minutes: 60,
  },
  {
    id: 'svc-consult',
    space_id: 'space-midtown',
    name: 'Strategy Consult',
    cost: 25,
    price: 180,
    category: 'Consulting',
    duration_minutes: 50,
  },
  {
    id: 'svc-detail',
    space_id: 'space-queens',
    name: 'Full Car Detailing',
    cost: 55,
    price: 220,
    category: 'Auto',
    duration_minutes: 120,
  },
  {
    id: 'svc-color',
    space_id: 'space-brooklyn',
    name: 'Color Treatment',
    cost: 35,
    price: 145,
    category: 'Grooming',
    duration_minutes: 90,
  },
];
