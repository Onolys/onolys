import { createRoot } from 'react-dom/client';
import { createAuthSession } from './auth/session';
import { createFirebaseProvider } from './auth/firebase';
import { getConfig } from './config';
import { Root } from './Root';

const session = createAuthSession(createFirebaseProvider(getConfig().firebase));
createRoot(document.getElementById('root')!).render(<Root session={session} />);
