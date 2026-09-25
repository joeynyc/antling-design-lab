const layers = {
  monitor: {
    src: 'assets/layer-monitor.png',
    alt: 'The widescreen monitor isolated on a transparent background.',
    caption: 'The monitor, screen, and stand as returned by the layer model.'
  },
  computer: {
    src: 'assets/layer-computer.png',
    alt: 'The compact desktop computer isolated on a transparent background.',
    caption: 'The compact computer separated from the rest of the desk scene.'
  },
  desk: {
    src: 'assets/layer-desk.png',
    alt: 'The wooden desk isolated on a transparent background.',
    caption: 'The wooden desk, including its top, front, and visible legs.'
  },
  wall: {
    src: 'assets/layer-wall.png',
    alt: 'The dark navy wall with violet ambient light.',
    caption: 'A clean crop of the wall layer and its violet ambient light.'
  }
};

const preview = document.querySelector('#layer-preview');
const stage = document.querySelector('#layer-stage');
const caption = document.querySelector('#layer-caption');
const download = document.querySelector('#layer-download');
const buttons = [...document.querySelectorAll('[data-layer]')];
let selectionToken = 0;

for (const button of buttons) {
  button.addEventListener('click', () => {
    const key = button.dataset.layer;
    const layer = layers[key];
    if (!layer || button.getAttribute('aria-pressed') === 'true') return;
    const token = ++selectionToken;
    buttons.forEach(item => {
      const active = item === button;
      item.classList.toggle('is-selected', active);
      item.setAttribute('aria-pressed', String(active));
    });
    preview.classList.add('is-loading');
    download.removeAttribute('href');
    download.setAttribute('aria-disabled', 'true');
    const nextImage = new Image();
    nextImage.onload = () => {
      if (token !== selectionToken) return;
      preview.src = layer.src;
      preview.alt = layer.alt;
      stage.dataset.layer = key;
      caption.textContent = layer.caption;
      download.href = layer.src;
      download.download = `antling-${key}.png`;
      download.removeAttribute('aria-disabled');
      preview.classList.remove('is-loading');
    };
    nextImage.onerror = () => {
      if (token !== selectionToken) return;
      caption.textContent = 'This layer could not be loaded. Try another layer.';
      preview.classList.remove('is-loading');
    };
    nextImage.src = layer.src;
  });
}
