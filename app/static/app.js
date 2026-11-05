const fixtures = {
evt_1001:{event_id:'evt_1001',order_reference:'ORD-2048',customer:'Avery Chen',product:'Mechanical keyboard',total_cents:12900},
evt_1002:{event_id:'evt_1002',order_reference:'ORD-2049',customer:'Morgan Lee',product:'Studio headphones',total_cents:8900},
evt_1003:{event_id:'evt_1003',order_reference:'ORD-2050',customer:'Jordan Ellis',product:'USB-C dock',total_cents:14900},
evt_1004:{event_id:'evt_1004',order_reference:'ORD-2051',customer:'Sam Rivera',product:'Desk light',total_cents:5900}};
const $=id=>document.getElementById(id);
const money=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
const esc=text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let busy=false;
function choose(){const e=fixtures[$('event').value];$('reference').textContent=e.order_reference;$('product').textContent=e.product;$('amount').textContent=money(e.total_cents);}
async function refresh(){
const response=await fetch('api/state');if(!response.ok)throw new Error('State request failed: '+response.status);
const data=await response.json(),s=data.summary;
$('deliveries-count').textContent=s.deliveries;$('events-count').textContent=s.unique_events;$('orders-count').textContent=s.orders;$('extras-count').textContent=s.extra_orders;
$('extra-card').classList.toggle('warning',s.extra_orders>0);$('order-label').textContent=s.orders+' saved';$('empty').hidden=s.orders>0;
$('orders-body').innerHTML=data.orders.map(o=>'<tr><td><b>#'+String(o.id).padStart(4,'0')+'</b><span class="secondary">'+esc(o.order_reference)+'</span></td><td>'+esc(o.customer)+'<span class="secondary">'+esc(o.product)+'</span></td><td><code>'+esc(o.event_id)+'</code></td><td>'+money(o.total_cents)+'</td></tr>').join('');
$('activity-body').innerHTML=data.deliveries.length?data.deliveries.map(d=>'<span class="delivery '+(d.status>=400?'failed':'')+'">'+esc(d.event_id)+'<b>'+d.status+' '+esc(d.outcome)+'</b></span>').join(''):'<p class="muted">No deliveries yet.</p>';
}
async function send(count,parallel=false,fail=false){
if(busy)return;busy=true;document.querySelectorAll('button,select').forEach(b=>b.disabled=true);
const event=fixtures[$('event').value];$('result').textContent='Sending '+count+(parallel?' concurrent':' sequential')+' request(s) for '+event.event_id+'...';
try{
const deliver=async()=>{const headers={'Content-Type':'application/json'};if(fail)headers['X-Demo-Fail-Before-Commit']='1';const r=await fetch('webhooks/orders',{method:'POST',headers,body:JSON.stringify(event)});await r.json();return r.status;};
const statuses=[];
if(parallel)statuses.push(...await Promise.all(Array.from({length:count},deliver)));
else for(let i=0;i<count;i++){statuses.push(await deliver());await refresh();if(i<count-1)await new Promise(resolve=>setTimeout(resolve,180));}
const counts={};statuses.forEach(s=>counts[s]=(counts[s]||0)+1);
$('result').textContent=count+(parallel?' concurrent':' sequential')+' deliveries sent for '+event.event_id+'.\n'+Object.entries(counts).map(([s,n])=>n+' response(s): HTTP '+s).join(' | ');
await refresh();
}catch(e){$('result').textContent='Request failed: '+e.message;}
finally{busy=false;document.querySelectorAll('button,select').forEach(b=>b.disabled=false);}
}
$('repeat').onclick=()=>send(5);$('once').onclick=()=>send(1);$('concurrent').onclick=()=>send(10,true);$('fail').onclick=()=>send(1,false,true);$('event').onchange=choose;
$('reset').onclick=async()=>{if(!confirm('Clear all demo orders and delivery history? Code changes are kept.'))return;const r=await fetch('api/demo/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:'reset-demo-data'})});if(!r.ok){$('result').textContent='Reset failed: HTTP '+r.status;return;}$('result').textContent='Demo data cleared. Ready for a new run.';await refresh();};
choose();refresh().catch(e=>$('result').textContent=e.message);setInterval(()=>{if(!busy)refresh().catch(()=>{});},2000);
