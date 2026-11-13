// Reuse the approved raster artwork through CSS viewports, without redrawing its lettering.
// The repeated asset is served once and reused from the browser cache.
export const brandSymbol = () => '<span class="brand-symbol" aria-hidden="true"><img src="/static/brand/kanella-master.png" alt="" width="1536" height="1024" decoding="async"></span>';
export const brandPattern = () => `<div class="brand-pattern" aria-hidden="true">${Array.from({length:12},()=>brandSymbol()).join('')}</div>`;

export const brandDetail = name => `<img class="brand-detail" src="/static/brand/elementos/${name}.svg" alt="" aria-hidden="true" width="48" height="48" loading="lazy">`;
