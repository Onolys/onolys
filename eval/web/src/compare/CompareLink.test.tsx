// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { EvalLink } from './CompareLink';
afterEach(cleanup);
it('intercepts only ordinary activation and retains real navigation for modified clicks',()=>{
 const navigate=vi.fn();render(<EvalLink state={{run:'r/1',view:'compare'}} navigate={navigate}>Compare</EvalLink>);
 const link=screen.getByRole('link');expect(link.getAttribute('href')).toContain('run=r%2F1');
 const click=new MouseEvent('click',{bubbles:true,cancelable:true,button:0});fireEvent(link,click);expect(click.defaultPrevented).toBe(true);expect(navigate).toHaveBeenCalledTimes(1);
 for(const modifier of ['ctrlKey','metaKey','altKey','shiftKey']){
  const event=new MouseEvent('click',{bubbles:true,cancelable:true,button:0,[modifier]:true});fireEvent(link,event);expect(event.defaultPrevented).toBe(false);
 }
 const middle=new MouseEvent('click',{bubbles:true,cancelable:true,button:1});fireEvent(link,middle);expect(middle.defaultPrevented).toBe(false);expect(navigate).toHaveBeenCalledTimes(1);
});
