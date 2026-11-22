import { render, screen } from '@testing-library/react';
import App from './App';

beforeEach(() => {
  global.fetch = jest.fn((url) => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(url.endsWith('/stats')
      ? { total: 1, verified: 0, unknown: 1, online: 1 }
      : [{ mac: 'aa:bb:cc:dd:ee:ff', ip: '192.168.1.5', status: 'Unknown', last_seen: '2026-01-01 00:00:00', online: true }]),
  }));
});

test('renders devices from the API', async () => {
  render(<App />);
  expect(await screen.findByText('aa:bb:cc:dd:ee:ff')).toBeInTheDocument();
  expect(screen.getByText(/BRIDGE_ACTIVE/)).toBeInTheDocument();
  expect(screen.getByText('IDENTIFY')).toBeInTheDocument();
});
