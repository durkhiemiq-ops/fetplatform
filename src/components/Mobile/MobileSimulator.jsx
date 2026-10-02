import React, { useEffect, useRef, useState } from 'react';
import { Smartphone, RotateCw, RefreshCw, ExternalLink, Wifi, Battery, Signal } from 'lucide-react';

const STATUS_BAR_HEIGHT = 30;

const DEVICES = [
  { id: 'iphone-14-pro', name: 'iPhone 14 Pro', width: 393, height: 852, notch: 'island' },
  { id: 'iphone-se', name: 'iPhone SE', width: 375, height: 667, notch: 'classic' },
  { id: 'pixel-7', name: 'Pixel 7', width: 412, height: 915, notch: 'punch' },
  { id: 'galaxy-s8', name: 'Galaxy S8', width: 360, height: 740, notch: 'classic' },
  { id: 'ipad-mini', name: 'iPad Mini', width: 768, height: 1024, notch: 'none' },
];

const Notch = ({ type }) => {
  if (type === 'island') {
    return <div className="absolute top-2 left-1/2 -translate-x-1/2 w-24 h-6 bg-black rounded-full z-20" />;
  }
  if (type === 'classic') {
    return <div className="absolute top-0 left-1/2 -translate-x-1/2 w-40 h-5 bg-black rounded-b-2xl z-20" />;
  }
  if (type === 'punch') {
    return <div className="absolute top-2.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-black rounded-full z-20" />;
  }
  return null;
};

const StatusBar = ({ time }) => (
  <div
    className="relative flex items-center justify-between px-6 bg-white text-text-primary text-xs font-semibold z-10"
    style={{ height: STATUS_BAR_HEIGHT }}
  >
    <span>{time}</span>
    <div className="flex items-center gap-1.5">
      <Signal size={13} />
      <Wifi size={13} />
      <Battery size={16} />
    </div>
  </div>
);

const EmbeddedNotice = () => (
  <div className="flex items-center justify-center min-h-[60vh]">
    <div className="fet-card p-8 text-center max-w-md">
      <Smartphone size={36} className="mx-auto text-primary" />
      <h3 className="text-lg font-semibold text-text-primary mt-3">Mobile Simulator</h3>
      <p className="text-sm text-text-secondary mt-1">
        The simulator is already active in this preview frame. Open the app in a browser tab to use it.
      </p>
    </div>
  </div>
);

const Simulator = () => {
  const [deviceId, setDeviceId] = useState(DEVICES[0].id);
  const [rotated, setRotated] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [scale, setScale] = useState(1);
  const [now, setNow] = useState(new Date());
  const containerRef = useRef(null);

  const device = DEVICES.find(d => d.id === deviceId) || DEVICES[0];
  const width = rotated ? device.height : device.width;
  const height = rotated ? device.width : device.height;
  const isTablet = device.id === 'ipad-mini';
  const outerRadius = isTablet ? 28 : 52;
  const innerRadius = outerRadius - 12;

  useEffect(() => {
    const update = () => {
      const el = containerRef.current;
      if (!el) return;
      const availableW = el.clientWidth - 32;
      const availableH = Math.max(window.innerHeight - 300, 320);
      setScale(Math.min(1, availableW / (width + 32), availableH / (height + 32)));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [width, height]);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30000);
    return () => clearInterval(timer);
  }, []);

  const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-[22px] font-bold text-text-primary">Mobile Simulator</h2>
        <p className="text-[13px] text-text-secondary">Preview the app live on a simulated device</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {DEVICES.map(d => (
          <button
            key={d.id}
            onClick={() => { setDeviceId(d.id); setRotated(false); }}
            className={`px-3 py-2 rounded-xl text-[12px] font-semibold border transition-colors ${
              deviceId === d.id
                ? 'bg-primary text-white border-primary'
                : 'bg-white text-text-secondary border-border-default hover:border-primary/40 hover:text-text-primary'
            }`}
          >
            {d.name}
          </button>
        ))}

        <div className="flex items-center gap-2 sm:ml-auto">
          <button
            onClick={() => setRotated(r => !r)}
            title="Rotate device"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] font-semibold bg-white text-text-secondary border border-border-default hover:border-primary/40 hover:text-text-primary transition-colors"
          >
            <RotateCw size={14} /> Rotate
          </button>
          <button
            onClick={() => setReloadKey(k => k + 1)}
            title="Reload preview"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-[12px] font-semibold bg-white text-text-secondary border border-border-default hover:border-primary/40 hover:text-text-primary transition-colors"
          >
            <RefreshCw size={14} /> Reload
          </button>
          <button
            onClick={() => window.open('/', '_blank', 'noopener')}
            title="Open app in a new tab"
            className="fet-btn-primary inline-flex items-center gap-1.5 px-3 py-2 !rounded-xl text-[12px]"
          >
            <ExternalLink size={14} /> Open
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="fet-card p-4 flex justify-center overflow-hidden"
      >
        <div
          style={{
            width: (width + 32) * scale,
            height: (height + 32) * scale,
          }}
        >
          <div
            style={{
              width: width + 32,
              height: height + 32,
              borderRadius: outerRadius,
              transform: `scale(${scale})`,
              transformOrigin: 'top left',
            }}
            className="p-4 bg-gradient-to-b from-[#2b2b2f] to-[#141416] shadow-2xl"
          >
            <div
              className="relative overflow-hidden bg-white"
              style={{ width, height, borderRadius: innerRadius }}
            >
              <Notch type={device.notch} />
              <StatusBar time={time} />
              <iframe
                key={reloadKey}
                src="/"
                title="Mobile Preview"
                className="border-0 bg-white block"
                style={{ width, height: height - STATUS_BAR_HEIGHT }}
              />
            </div>
          </div>
        </div>
      </div>

      <p className="text-xs text-text-secondary text-center">
        {device.name} • {width} × {height} px • {rotated ? 'Landscape' : 'Portrait'}
        {scale < 1 ? ` • scaled to ${Math.round(scale * 100)}%` : ''}
      </p>
    </div>
  );
};

const MobileSimulator = () => {
  const isEmbedded = window.self !== window.top;
  return isEmbedded ? <EmbeddedNotice /> : <Simulator />;
};

export default MobileSimulator;
