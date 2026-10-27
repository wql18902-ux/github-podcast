import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Button } from './vendor/lwq/Button';
import { SearchField } from './vendor/lwq/Field';
import { InlineFeedback } from './vendor/lwq/Feedback';
import { NeonLanding } from './griffin-landing';

// These are the downloaded originals, not lookalikes. Scoped CSS maps their
// data-variant/data-size contract onto Sourcecast's existing semantic tokens.

function NoteSearch() {
  const [value, setValue] = useState('');
  return <SearchField label="搜索笔记" placeholder="搜索标题或正文" value={value} onChange={value => {
    setValue(value);
    window.dispatchEvent(new CustomEvent('sourcecast:note-search', { detail: value }));
  }} />;
}

const landing = document.getElementById('neonLanding');
if (landing) createRoot(landing).render(<NeonLanding />);

document.querySelectorAll<HTMLElement>('[data-lwq-action]').forEach(host => {
  const anchor = host.querySelector<HTMLAnchorElement>('a');
  if (!anchor) return;
  const href = anchor.getAttribute('href') || '#home';
  const text = anchor.textContent;
  const variant = host.dataset.lwqAction === 'quiet' ? 'ghost' : 'default';
  createRoot(host).render(<Button asChild variant={variant} size="lg" className="lwq-button"><a href={href}>{text}</a></Button>);
  host.dataset.componentSource = 'lwq/button';
});

const search = document.querySelector('#lwqNoteSearch');
if (search) createRoot(search).render(<NoteSearch />);
const feedback = document.querySelector('#lwqNoteHint');
if (feedback) createRoot(feedback).render(<InlineFeedback presentation="plain">笔记与导图直接就能用。接上自己的模型服务以后，还能把材料整理成笔记。</InlineFeedback>);

document.documentElement.dataset.lwqComponents = 'ready';
