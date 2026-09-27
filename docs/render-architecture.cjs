// Render the architecture with the same bundled fonts as the merchant console.
const fs = require('fs');
const path = require('path');
const { chromium } = require('C:/Users/AD/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = path.join(__dirname, '..');
const media = path.join(root, 'bondlayer/app/out/_next/static/media');
const font = name => fs.readFileSync(path.join(media, name)).toString('base64');
const logo = fs.readFileSync(path.join(__dirname, 'bondlayer-logo.svg'), 'utf8')
  .replace('<rect width="1194" height="315" fill="white"/>', '')
  .replace(/<svg[^>]*>/, '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1238 315">');
const logoData = Buffer.from(logo).toString('base64');
const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;');
const text = (x,y,s,cls='body',extra='') => `<text x="${x}" y="${y}" class="${cls}" ${extra}>${esc(s)}</text>`;
const lines = (x,y,ss,cls='body',step=30) => ss.map((s,i)=>text(x,y+i*step,s,cls)).join('');
const icons = {
 console:'<rect x="3" y="3" width="26" height="19" rx="3"/><path d="M0 28h32M12 22v6m8-6v6"/>',
 csv:'<path d="M6 1h14l7 7v23H6zM20 1v8h7M10 15h13M10 21h13M10 27h13M16 15v12"/>',
 policy:'<path d="M6 1h14l7 7v23H6zM20 1v8h7M11 15h10M11 21h10M11 27h6"/>',
 check:'<path d="M5 17l7 7L28 7"/>',
 extract:'<path d="M6 1h14l7 7v23H6zM20 1v8h7M11 15h10M11 21h7"/>',
 shield:'<path d="M16 1L29 6v9c0 8-7 14-13 17C10 29 3 23 3 15V6zM9 16l5 5 10-11"/>',
 storage:'<ellipse cx="16" cy="6" rx="13" ry="5"/><path d="M3 6v20c0 7 26 7 26 0V6M3 16c0 7 26 7 26 0"/>',
 api:'<circle cx="16" cy="5" r="4"/><circle cx="5" cy="27" r="4"/><circle cx="27" cy="27" r="4"/><path d="M14 9L7 23M18 9l7 14M9 27h14"/>',
 agent:'<rect x="2" y="8" width="28" height="23" rx="6"/><path d="M16 8V1M10 24h12"/><circle cx="10" cy="17" r="1"/><circle cx="22" cy="17" r="1"/>',
 user:'<circle cx="16" cy="8" r="7"/><path d="M3 31v-3a13 13 0 0126 0v3z"/>',
 chart:'<path d="M2 1v30h29M8 23l7-9 7 4 9-13"/>',
 spark:'<path d="M16 1l4 11 11 4-11 4-4 11-4-11L1 16l11-4z"/>'
};
function card(x,y,w,h,title,body,icon,color='teal',opts={}) {
 return `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="22" fill="white" stroke="#e3e8ef" stroke-width="2"/>
 <rect x="${x+24}" y="${y+24}" width="52" height="52" rx="15" class="${color}Soft"/>
 <g transform="translate(${x+34} ${y+34})" fill="none" class="${color}Stroke" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icons[icon]}</g>
 ${text(x+92,y+47,title,'cardTitle')}${lines(x+24,y+(opts.bodyY||108),body,'body',29)}${opts.extra||''}</g>`;
}
const arrow=(d,feedback=false,both=false)=>`<path d="${d}" fill="none" stroke="${feedback?'#198876':'#82919f'}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" ${feedback?'stroke-dasharray="8 8"':''} marker-end="url(#${feedback?'green':'arrow'})" ${both?'marker-start="url(#start)"':''}/>`;
const lane=(x,w,n,title,color)=>`<rect x="${x}" y="214" width="${w}" height="50" rx="25" class="${color}Soft"/>${text(x+22,247,n,'laneNumber')}${text(x+63,247,title,'laneTitle')}`;
const boundary=(x,y,w,h,color,label)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="30" fill="none" stroke="${color}" stroke-width="2"/><rect x="${x+24}" y="${y-14}" width="${label.length*13+36}" height="28" rx="14" fill="#f6f8fb"/>${text(x+42,y+7,label,'boundaryLabel')}`;
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="2100" height="1400" viewBox="0 0 2100 1400">
<defs><style>
@font-face{font-family:SpaceGrotesk;src:url(data:font/woff2;base64,${font('36966cca54120369-s.p.woff2')}) format('woff2');font-weight:300 700}
@font-face{font-family:Figtree;src:url(data:font/woff2;base64,${font('de42cfb9a3b980ae-s.p.woff2')}) format('woff2');font-weight:300 900}
text{fill:#172033;font-family:Figtree,sans-serif}.title{font-family:SpaceGrotesk;font-size:58px;font-weight:600;letter-spacing:-2px}.brand{font-family:SpaceGrotesk;font-size:26px;font-weight:650}.subtitle{font-size:24px;fill:#68768a}.cardTitle{font-family:SpaceGrotesk;font-size:23px;font-weight:600;letter-spacing:-.5px}.body{font-size:21px;fill:#68768a}.small{font-size:18px;fill:#68768a}.laneTitle{font-family:SpaceGrotesk;font-size:23px;font-weight:600}.laneNumber{font-size:17px;font-weight:650;fill:#68768a}.boundaryLabel{font-family:SpaceGrotesk;font-size:17px;font-weight:600;letter-spacing:.5px}.label{font-size:17px;fill:#198876}.tealSoft{fill:#e6f6f3}.greenSoft{fill:#edf6dd}.yellowSoft{fill:#fff3cc}.tealStroke{stroke:#0f766e}.greenStroke{stroke:#647f30}.yellowStroke{stroke:#ac7c13}
</style><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M1 1L9 5L1 9" fill="none" stroke="#82919f" stroke-width="1.5"/></marker><marker id="start" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M9 1L1 5L9 9" fill="none" stroke="#82919f" stroke-width="1.5"/></marker><marker id="green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M1 1L9 5L1 9" fill="none" stroke="#198876" stroke-width="1.5"/></marker></defs>
<rect width="2100" height="1400" fill="#f6f8fb"/>
<image x="64" y="36" width="210" height="54" href="data:image/svg+xml;base64,${logoData}" preserveAspectRatio="xMinYMid meet"/>
${text(70,148,'System architecture','title')}${text(1100,141,'From merchant data to agent-ready commerce','subtitle')}
${lane(70,370,'01','Merchant inputs','yellow')}${lane(510,1040,'02','BondLayer merchant service','teal')}${lane(1620,410,'03','Shopping experience','green')}
${text(1530,247,'FastAPI','small','text-anchor="end"')}
${boundary(42,286,426,850,'#d8b55b','MERCHANT')}
${boundary(482,286,1096,850,'#55a89d','BONDLAYER')}
${boundary(1592,286,466,850,'#91ad58','CUSTOMER')}
${card(70,310,370,150,'Merchant console',['Onboarding · Catalogue · Policies','Dashboard & insights · Next.js'],'console','yellow')}
${card(70,550,370,140,'Catalogue CSV',['Products, prices & attributes'],'csv','yellow')}
${card(70,770,370,140,'Policy document',['Returns, warranty & benefits'],'policy','yellow')}
${card(570,310,920,150,'Insights & activity',['Comparison reports show merchants how their offers perform.'],'chart')}
${card(510,550,320,140,'Validate catalogue',['Check & normalise rows'],'check')}
${card(510,770,320,140,'Extract benefits',['Create policy drafts'],'extract')}
${card(510,980,320,140,'Review & sign',['Merchant approves terms'],'shield')}
${card(930,655,270,180,'Storage',['Catalogues · Benefits','Signing keys'],'storage')}
${card(1290,655,260,180,'UCP API',['Discovery · Search','Intent · Checkout'],'api')}
${card(1620,310,410,150,'Shopper',['Asks for a product'],'user','green')}
${card(1620,620,410,370,'Shopping agent',['Understand the request','Fetch offers & verify records','Compare & rank','Confirm checkout'],'agent','green',{extra:text(1644,959,'Buyer demo · FastAPI','small')})}
${arrow('M440 620H510')}${arrow('M440 840H510')}
${arrow('M830 620H1065V655')}${arrow('M670 910V980')}${arrow('M830 1050H1065V835')}
${arrow('M1200 745H1290')}${arrow('M1550 745H1620',false,true)}${arrow('M1825 460V620',false,true)}
${text(1839,545,'Conversation','small')}
${arrow('M1620 675H1585V515H1180V460',true)}${text(1260,501,'Comparison reports','label')}
${arrow('M570 385H440',true)}
${text(1090,944,'Approved records only','small')}
<rect x="70" y="1200" width="1960" height="116" rx="24" fill="#fff" stroke="#e3e8ef" stroke-width="2"/>
<rect x="94" y="1232" width="52" height="52" rx="15" fill="#fff3cc"/><g transform="translate(104 1242)" fill="none" stroke="#ac7c13" stroke-width="2" stroke-linejoin="round">${icons.spark}</g>
${text(165,1247,'AI support · OpenAI','cardTitle')}${text(165,1282,'Policy extraction · Merchant answers · Request understanding · Live ranking','body')}
${text(1300,1247,'Offline rules mode','cardTitle')}${text(1300,1282,'Reference ranking + bundled demo policy drafts','body')}
${text(70,1363,'Space Grotesk / Figtree · BondLayer system overview','small')}
${arrow('M1480 1357H1540')}${text(1560,1363,'Data / API','small')}${arrow('M1770 1357H1830',true)}${text(1850,1363,'Activity feedback','small')}
</svg>`;
(async()=>{
 const output = path.join(__dirname,'bondlayer-architecture-v3');
 fs.writeFileSync(output+'.svg',svg);
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
 const page=await browser.newPage({viewport:{width:2100,height:1400},deviceScaleFactor:1.5});
 await page.setContent(`<html><body style="margin:0">${svg}</body></html>`);
 await page.evaluate(()=>document.fonts.ready);
 const loaded=await page.evaluate(()=>({heading:document.fonts.check('600 23px SpaceGrotesk'),body:document.fonts.check('21px Figtree')}));
 if(!loaded.heading||!loaded.body)throw new Error('App fonts did not load');
 await page.screenshot({path:output+'.png'});
 console.log(JSON.stringify({fonts:loaded,image:output+'.png',editable:output+'.svg'}));
 }finally{await browser.close()}
})();
