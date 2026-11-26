import { createRoot } from 'react-dom/client';
import { createFirebaseAuthService } from '@prod-auth/firebaseService';
import { redirectToCanonicalHost } from './canonicalHost';
import { getConfig } from './config';
import { Root } from './Root';

// The prod login component (one copy), pointed at eval's own Identity Platform project (onolys-eval). No /v1 email
// API and no sign-up here: accounts are created by the operator script infra/scripts/create-test-user.py.
// A trailing-dot host is a different CORS origin: move to the canonical host before booting.
if (!redirectToCanonicalHost(window.location)) {
  const service = createFirebaseAuthService(getConfig().firebase, { emailApi: null });
  createRoot(document.getElementById('root')!).render(<Root service={service} />);
}
