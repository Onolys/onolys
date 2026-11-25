import { createRoot } from 'react-dom/client';
import { createFirebaseAuthService } from '@prod-auth/firebaseService';
import { getConfig } from './config';
import { Root } from './Root';

// The prod login, one copy: same Firebase web app, auth domain eval.onolys.com. No /v1 email API here:
// sign-up, verification and reset emails are sent from the prod app.
const service = createFirebaseAuthService(getConfig().firebase, { emailApi: null });
createRoot(document.getElementById('root')!).render(<Root service={service} />);
