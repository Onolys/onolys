import { Button } from '@onolys/common';
import { ApiError } from '../../api';
import type { Snippet } from '../compareApi';

export function ErrorNotice({ error, retry }: { error: unknown; retry: () => void }) {
 return <div role="alert">{error instanceof ApiError && error.code === 'transcript_changed' ? 'The saved transcript changed since this run; lines cannot be shown.' : error instanceof Error ? error.message : 'Could not load saved output.'}<Button onClick={retry}>Retry</Button></div>;
}
/** Saved rationale text, verbatim (whitespace preserved); empty rationale shows as withheld. */
export function Snippets({ snippets }: { snippets: Snippet[] }) {
 return <>{snippets.map((snippet, i) => <article key={i}><p>Repeat {snippet.repeat}</p><p className="line-verbatim">{snippet.rationale === '' ? 'withheld' : snippet.rationale}</p>{snippet.quote_verified && snippet.quote != null && <blockquote className="line-verbatim">{snippet.quote}</blockquote>}{snippet.evidence?.map((item, j) => <blockquote key={j}><span>{item.turn_id}</span><p className="line-verbatim">{item.quote}</p></blockquote>)}</article>)}</>;
}
