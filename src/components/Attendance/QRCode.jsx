import React from 'react';
import { QRCodeSVG } from 'qrcode.react';

const QRCodeDisplay = ({ value, size = 200, className = '' }) => {
  if (!value) return null;
  return (
    <QRCodeSVG
      value={value}
      size={size}
      level="M"
      className={className}
      fgColor="#0F0B3D"
    />
  );
};

export default QRCodeDisplay;