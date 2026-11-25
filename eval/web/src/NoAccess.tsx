import { Button } from '@onolys/ui';
import { useSignOut } from '@prod-auth/useSignOut';

/** Signed in, but the eval backend answered 403. Sign-out stays available. */
export function NoAccess({ code }: { code?: string }) {
  const { signOut, error } = useSignOut();
  return <div className="app-message" role="alert">
    <h2>No access</h2>
    <p>{code === 'email_unverified'
      ? 'Verify your email in the Onolys app, then sign out and sign in again.'
      : code === 'not_allowlisted'
        ? 'This account is not on the access list for this app. Ask the owner to add you.'
        : 'This account is not allowed to use this app, or its email is not verified.'}</p>
    {error && <p>{error}</p>}
    <Button type="button" onClick={() => void signOut()}>Sign out</Button>
  </div>;
}
