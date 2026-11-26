import { createRoot } from 'react-dom/client';
import { createFirebaseAuthService } from '@prod-auth/firebaseService';
import { getConfig } from './config';
import { Root } from './Root';

// The prod login component (one copy), pointed at eval's own Identity Platform project (onolys-eval). No /v1 email
// API and no sign-up here: accounts are created by the operator script infra/scripts/create-test-user.py.
const service = createFirebaseAuthService(getConfig().firebase, { emailApi: null });
createRoot(document.getElementById('root')!).render(<Root service={service} />);
