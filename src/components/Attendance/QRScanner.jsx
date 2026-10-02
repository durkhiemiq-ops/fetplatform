import React, { useState, useEffect, useRef } from 'react';
import { QrCode, X, CheckCircle, AlertCircle, Camera, Keyboard } from 'lucide-react';
import api from '../../lib/api';

const BarcodeDetectorApi = typeof window !== 'undefined' ? (window.BarcodeDetector || null) : null;

const QRScanner = ({ onClose, onScan }) => {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [manualCode, setManualCode] = useState('');
  const [cameraOn, setCameraOn] = useState(false);
  const [cameraError, setCameraError] = useState('');
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    setCameraOn(false);
  };

  useEffect(() => {
    return () => stopCamera();
  }, []);

  const extractToken = (raw) => {
    // The QR encodes the raw token, but may be wrapped in a URL
    const text = String(raw || '').trim();
    const match = text.match(/([A-Za-z0-9_-]{20,})/);
    return match ? match[1] : text;
  };

  const submitScan = async (token) => {
    const clean = extractToken(token);
    if (!clean) {
      setError('Invalid QR code. Please try again.');
      return;
    }
    setScanning(true);
    setError('');
    try {
      const res = await api.post('/attendance/scan/', { token: clean });
      const data = res.data?.data ?? res.data;
      if (data?.success || res.status === 201) {
        setResult({
          success: true,
          message: data?.message || 'Attendance recorded.',
          time: new Date().toLocaleTimeString(),
        });
        if (onScan) onScan({ success: true, record: data });
        stopCamera();
      } else {
        setError(data?.message || 'Scan failed.');
        if (onScan) onScan({ success: false });
      }
    } catch (err) {
      const e = err.response?.data?.error;
      setError(e?.message || err.response?.data?.message || 'Scan failed. Please try again.');
      if (onScan) onScan({ success: false });
    } finally {
      setScanning(false);
    }
  };

  const startCamera = async () => {
    setCameraError('');
    if (!BarcodeDetectorApi) {
      setCameraError('Camera scanning is not supported in this browser. Use the code entry below.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Camera access is unavailable. Use the code entry below.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;
      setCameraOn(true);
      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        await video.play();
        await scanLoop(video);
      }
    } catch (err) {
      setCameraError('Could not access the camera: ' + (err?.message || 'Permission denied.'));
    }
  };

  const scanLoop = async (video) => {
    if (!video || !BarcodeDetectorApi) return;
    const detector = new BarcodeDetectorApi({ formats: ['qr_code'] });
    let stop = false;
    const loop = async () => {
      if (stop) return;
      try {
        const codes = await detector.detect(video);
        if (codes.length > 0) {
          stop = true;
          stopCamera();
          await submitScan(codes[0].rawValue);
          return;
        }
      } catch {
        // continue scanning
      }
      if (!stop) setTimeout(loop, 200);
    };
    loop();
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    if (!manualCode) {
      setError('Please enter the attendance code');
      return;
    }
    submitScan(manualCode);
    setManualCode('');
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="fet-card bg-white rounded-2xl shadow-modal max-w-md w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-text-primary">Scan QR Code</h3>
          <button onClick={() => { stopCamera(); onClose(); }} className="p-1 hover:bg-page-bg rounded-lg">
            <X size={24} className="text-text-secondary" />
          </button>
        </div>

        {result?.success ? (
          <div className="text-center py-6">
            <CheckCircle size={64} className="mx-auto text-success mb-4" />
            <h4 className="text-xl font-bold text-success">Attendance Recorded</h4>
            <p className="text-text-secondary mt-2">{result.message}</p>
            <p className="text-text-secondary">Time: {result.time}</p>
            <button
              onClick={() => { stopCamera(); onClose(); }}
              className="mt-4 fet-btn-primary"
            >
              Done
            </button>
          </div>
        ) : (
          <>
            {cameraOn && (
              <div className="rounded-xl overflow-hidden bg-black relative">
                <video ref={videoRef} className="w-full h-64 object-cover" playsInline muted />
                <div className="absolute inset-0 border-2 border-primary rounded-xl pointer-events-none overlay-frame" />
                <p className="absolute bottom-2 left-0 right-0 text-center text-white text-xs bg-black/50 py-1">
                  {scanning ? 'Recording attendance...' : 'Point camera at the QR code'}
                </p>
              </div>
            )}

            {!cameraOn && (
              <div className="border-2 border-dashed border-border-default rounded-xl p-8 text-center">
                {cameraError ? (
                  <div>
                    <AlertCircle size={40} className="mx-auto text-warning mb-2" />
                    <p className="text-sm text-text-secondary">{cameraError}</p>
                  </div>
                ) : (
                  <div>
                    <QrCode size={64} className="mx-auto text-primary" />
                    <p className="text-text-secondary mt-2">Use your camera to scan the QR code</p>
                  </div>
                )}
                <button
                  onClick={startCamera}
                  disabled={scanning}
                  className="mt-4 fet-btn-primary flex items-center gap-2 mx-auto"
                >
                  <Camera size={18} />
                  Start Camera
                </button>
              </div>
            )}

            <div className="mt-4">
              <p className="text-sm text-text-secondary text-center mb-2 flex items-center justify-center gap-1">
                <Keyboard size={14} /> OR enter the code shown under the QR
              </p>
              <form onSubmit={handleManualSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={manualCode}
                  onChange={(e) => setManualCode(e.target.value)}
                  placeholder="Enter attendance code"
                  className="flex-1 fet-input uppercase"
                />
                <button
                  type="submit"
                  disabled={scanning}
                  className="fet-btn-primary"
                >
                  {scanning ? 'Checking...' : 'Submit'}
                </button>
              </form>
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-danger text-sm flex items-center gap-2">
                <AlertCircle size={18} />
                {error}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default QRScanner;