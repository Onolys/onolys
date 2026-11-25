// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { EvalLink } from './CompareLink';
import { ChartFrame } from './ChartFrame';
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
it('places how-to-read directly below a chart and provides its table twin',()=>{
 render(<ChartFrame title="Example" howToRead="Longer bars mean more lines." table={<table><caption>Example values</caption><tbody><tr><th scope="row">A</th><td>2</td></tr></tbody></table>}><svg aria-label="Example chart"/></ChartFrame>);
 expect(screen.getByText('Longer bars mean more lines.').previousElementSibling?.querySelector('svg')).toBeTruthy();
 expect(screen.getByText('Show data table for Example')).toBeTruthy();expect(screen.getByText('Example values')).toBeTruthy();
});
