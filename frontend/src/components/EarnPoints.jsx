// src/components/EarnPoints.jsx

import React, { useState, useEffect } from 'react';
import { apiUrl } from '../lib/api';

const EarnPoints = ({ updatePoints }) => {
    const [file, setFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [loading, setLoading] = useState(false);
    const [detailedLoading, setDetailedLoading] = useState(false);
    const [detectionResult, setDetectionResult] = useState(null);
    const [detailedAnalysis, setDetailedAnalysis] = useState(null);
    const [error, setError] = useState(null);
    const [expandedItems, setExpandedItems] = useState(new Set());
    const [isMobile, setIsMobile] = useState(false);
    const [inputType, setInputType] = useState('photo'); // 'photo', 'video_gallery', 'video_camera'
    const [offlineQueue, setOfflineQueue] = useState([]);

    // Mobile device detection
    useEffect(() => {
        const checkMobile = () => {
            const userAgent = navigator.userAgent || navigator.vendor || window.opera;
            const isMobileDevice = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(userAgent.toLowerCase());
            const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
            setIsMobile(isMobileDevice || isTouchDevice);
        };
        
        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);

    const handleFileChange = (event) => {
        const selectedFile = event.target.files[0];
        if (selectedFile) {
            setFile(selectedFile);
            setPreviewUrl(URL.createObjectURL(selectedFile));
            setDetectionResult(null);
            setDetailedAnalysis(null);
            setError(null);
            setExpandedItems(new Set());
        }
    };

    const handleInputTypeChange = (type) => {
        setInputType(type);
        setFile(null);
        setPreviewUrl(null);
        setDetectionResult(null);
        setDetailedAnalysis(null);
        setError(null);
        setExpandedItems(new Set());
    };

    const toggleItemExpansion = (itemIndex) => {
        const newExpanded = new Set(expandedItems);
        if (newExpanded.has(itemIndex)) {
            newExpanded.delete(itemIndex);
        } else {
            newExpanded.add(itemIndex);
        }
        setExpandedItems(newExpanded);
    };

    const getDetailedAnalysis = async () => {
        if (!file) {
            setError('Please select an image first!');
            return;
        }

        const token = localStorage.getItem('authToken');
        if (!token) {
            setError('You must be logged in to get detailed analysis.');
            return;
        }

        setDetailedLoading(true);
        setError(null);

        try {
            const formData = new FormData();
            
            // Append file with appropriate field name based on input type
            if (inputType === 'photo') {
                formData.append('photo_file', file);
            } else if (inputType === 'video_gallery') {
                formData.append('video_gallery_file', file);
            } else if (inputType === 'video_camera') {
                formData.append('video_camera_file', file);
            }
            
            // Add input type to form data
            formData.append('input_type', inputType);

            const res = await fetch(apiUrl('/api/analyze-detailed'), {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                if (data?.duplicate) {
                    setError('This exact image has already been analyzed. Please upload a different image.');
                } else {
                    setError(data?.error || 'Detailed analysis failed.');
                }
                setDetailedLoading(false);
                return;
            }

            setDetailedAnalysis(data);
        } catch {
            setError('Network error. Please try again.');
        } finally {
            setDetailedLoading(false);
        }
    };

    const handleSubmit = async () => {
        if (!file) {
            alert("Please select an image first!");
            return;
        }

        const token = localStorage.getItem('authToken');
        if (!token) {
            setError('You must be logged in to earn points.');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const formData = new FormData();
            
            // Append file with appropriate field name based on input type
            if (inputType === 'photo') {
                formData.append('photo_file', file);
            } else if (inputType === 'video_gallery') {
                formData.append('video_gallery_file', file);
            } else if (inputType === 'video_camera') {
                formData.append('video_camera_file', file);
            }
            
            // Add input type to form data
            formData.append('input_type', inputType);

            const res = await fetch(apiUrl('/api/detect'), {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                if (data?.duplicate) {
                    setError('This exact image has already been analyzed. Please upload a different image.');
                } else {
                    setError(data?.error || 'Detection failed.');
                }
                setLoading(false);
                return;
            }

            const result = {
                awarded_points: data.awarded_points,
                detected_items: data.detected_items,
                recyclable_items: data.recyclable_items,
                hazardous_items: data.hazardous_items,
                general_items: data.general_items || [],
                duplicate: data.duplicate,
                message: data.message,
                gemini_analysis: data.gemini_analysis || {}
            };

            setDetectionResult(result);

            if (typeof data.total_points === 'number') {
                updatePoints(data.total_points);
            }
        } catch (e) {
            if (typeof navigator !== 'undefined' && navigator.onLine === false) {
                try {
                    const reader = new FileReader();
                    reader.onload = () => {
                        const b64 = reader.result;
                        const item = { file_b64: b64, filename: file.name || 'upload.jpg', ts: Date.now() };
                        const prior = JSON.parse(localStorage.getItem('offlineQueue') || '[]');
                        const next = [...prior, item];
                        localStorage.setItem('offlineQueue', JSON.stringify(next));
                        setOfflineQueue(next);
                        setError(null);
                        alert('Waiting for network… item added to offline queue.');
                    };
                    reader.readAsDataURL(file);
                } catch {
                    setError('Offline and failed to queue upload.');
                }
            } else {
                setError('Network error. Please try again.');
            }
        } finally {
            setLoading(false);
        }
    };

    // Auto-upload queued items when online
    useEffect(() => {
        const sync = async () => {
            try {
                const token = localStorage.getItem('authToken');
                const queued = JSON.parse(localStorage.getItem('offlineQueue') || '[]');
                if (!queued.length) return;
                const res = await fetch(apiUrl('/api/upload/offline-sync'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                    body: JSON.stringify({ items: queued })
                });
                const data = await res.json();
                if (res.ok) {
                    localStorage.setItem('offlineQueue', JSON.stringify([]));
                    setOfflineQueue([]);
                    alert('Upload completed successfully!');
                }
            } catch { /* noop */ }
        };
        const onOnline = () => { sync(); };
        window.addEventListener('online', onOnline);
        sync();
        return () => window.removeEventListener('online', onOnline);
    }, []);

    const isSuccess = detectionResult && detectionResult.awarded_points > 0;
    const isDetected = detectionResult && (
        inputType === 'photo' 
            ? detectionResult.detected_items.length > 0
            : detectionResult.video_analysis?.disposal_verified === true
    );

    return (
        <div className="">
            <h3 className="text-2xl font-semibold text-gray-100 mb-6">Smart Waste Scan</h3>
            
            {/* Input Type Selection */}
            <div className="mb-6">
                <div className="flex flex-col sm:flex-row gap-3">
                    <button
                        onClick={() => handleInputTypeChange('photo')}
                        className={`flex-1 p-4 rounded-lg border-2 transition-all duration-300 ${
                            inputType === 'photo'
                                ? 'border-eco-green bg-eco-green/10 text-eco-green'
                                : 'border-white/20 bg-white/5 text-gray-300 hover:border-eco-green/40'
                        }`}
                    >
                        <div className="text-center">
                            <span className="text-3xl mb-2 block">📸</span>
                            <p className="font-medium">Upload Photo</p>
                            <p className="text-xs opacity-75">Select from gallery</p>
                        </div>
                    </button>
                    
                    <button
                        onClick={() => handleInputTypeChange('video_gallery')}
                        className={`flex-1 p-4 rounded-lg border-2 transition-all duration-300 ${
                            inputType === 'video_gallery'
                                ? 'border-eco-green bg-eco-green/10 text-eco-green'
                                : 'border-white/20 bg-white/5 text-gray-300 hover:border-eco-green/40'
                        }`}
                    >
                        <div className="text-center">
                            <span className="text-3xl mb-2 block">🖼️</span>
                            <p className="font-medium">Select Video</p>
                            <p className="text-xs opacity-75">From gallery</p>
                        </div>
                    </button>
                    
                    {isMobile && (
                        <button
                            onClick={() => handleInputTypeChange('video_camera')}
                            className={`flex-1 p-4 rounded-lg border-2 transition-all duration-300 ${
                                inputType === 'video_camera'
                                    ? 'border-eco-green bg-eco-green/10 text-eco-green'
                                    : 'border-white/20 bg-white/5 text-gray-300 hover:border-eco-green/40'
                            }`}
                        >
                            <div className="text-center">
                                <span className="text-3xl mb-2 block">🎥</span>
                                <p className="font-medium">Record Video</p>
                                <p className="text-xs opacity-75">Use camera</p>
                            </div>
                        </button>
                    )}
                </div>
            </div>
            
            <div className="flex flex-col md:flex-row space-y-6 md:space-y-0 md:space-x-8">
                {/* File Upload Area */}
                <div className="flex-1">
                    <div className="rounded-xl border-2 border-dashed border-white/20 bg-white/5 hover:border-eco-green/40 transition-colors p-10 h-64 flex flex-col items-center justify-center cursor-pointer">
                        {inputType === 'photo' && (
                            <>
                                <input 
                                    type="file" 
                                    onChange={handleFileChange} 
                                    accept="image/*" 
                                    className="hidden" 
                                    id="photo-upload" 
                                />
                                <label htmlFor="photo-upload" className="text-center">
                                    <span className="text-5xl text-gray-300 mb-2 block">📸</span>
                                    <p className="text-gray-300 font-medium">Drag & Drop or Click to Select Photo</p>
                                    {file && <p className="text-sm text-eco-green mt-1 font-semibold">File Selected: {file.name}</p>}
                                </label>
                            </>
                        )}
                        
                        {inputType === 'video_gallery' && (
                            <>
                                <input 
                                    type="file" 
                                    onChange={handleFileChange} 
                                    accept="video/*" 
                                    className="hidden" 
                                    id="video-gallery-upload" 
                                />
                                <label htmlFor="video-gallery-upload" className="text-center">
                                    <span className="text-5xl text-gray-300 mb-2 block">🖼️</span>
                                    <p className="text-gray-300 font-medium">Drag & Drop or Click to Select Video</p>
                                    {file && <p className="text-sm text-eco-green mt-1 font-semibold">File Selected: {file.name}</p>}
                                </label>
                            </>
                        )}
                        
                        {inputType === 'video_camera' && isMobile && (
                            <>
                                <input 
                                    type="file" 
                                    onChange={handleFileChange} 
                                    accept="video/*" 
                                    capture="environment"
                                    className="hidden" 
                                    id="video-camera-upload" 
                                />
                                <label htmlFor="video-camera-upload" className="text-center">
                                    <span className="text-5xl text-gray-300 mb-2 block">🎥</span>
                                    <p className="text-gray-300 font-medium">Tap to Record Video with Camera</p>
                                    {file && <p className="text-sm text-eco-green mt-1 font-semibold">File Selected: {file.name}</p>}
                                </label>
                            </>
                        )}
                    </div>

                    <div className="mt-4 space-y-3">
                        <button 
                            onClick={handleSubmit}
                            disabled={!file || loading}
                            className={`w-full py-3 text-lg font-bold rounded-lg transition duration-300 ${
                                !file || loading 
                                    ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed' 
                                    : 'bg-eco-green text-white hover:brightness-110'
                            }`}
                        >
                            {loading ? 'Running Waste Detection...' : 'Analyze & Earn'}
                        </button>
                        
                        {detectionResult && !detailedAnalysis && (
                            <button 
                                onClick={getDetailedAnalysis}
                                disabled={detailedLoading}
                                className={`w-full py-2 text-sm font-medium rounded-lg transition duration-300 ${
                                    detailedLoading 
                                        ? 'bg-blue-500/40 text-gray-300 cursor-not-allowed' 
                                        : 'bg-blue-500/20 text-blue-300 border border-blue-500/30 hover:bg-blue-500/30'
                                }`}
                            >
                                {detailedLoading ? 'Getting Detailed Analysis...' : '🧠 Get Detailed AI Analysis'}
                            </button>
                        )}
                    </div>
                </div>

                {/* Results and Preview Area */}
                <div className="flex-1 bg-white/5 border border-white/10 p-4 rounded-xl shadow-inner min-h-full">
                    <h4 className="text-lg font-semibold mb-4 border-b border-white/10 pb-2 text-gray-100">Live Preview & Results</h4>
                    
                    {previewUrl && (
                        <div className="w-full h-48 mb-4 rounded-lg shadow-md overflow-hidden">
                            {inputType === 'photo' ? (
                                <img src={previewUrl} alt="Waste Preview" className="w-full h-full object-contain" loading="lazy" decoding="async" />
                            ) : (
                                <video 
                                    src={previewUrl} 
                                    controls 
                                    className="w-full h-full object-contain"
                                    preload="metadata"
                                >
                                    Your browser does not support the video tag.
                                </video>
                            )}
                        </div>
                    )}

                    {loading && (
                         <div className="flex items-center space-x-2 text-eco-green">
                             <div className="w-4 h-4 border-t-2 border-eco-green rounded-full animate-spin"></div>
                             <span>Running Waste Detection...</span>
                         </div>
                    )}
                    
                    {detailedLoading && (
                         <div className="flex items-center space-x-2 text-blue-400">
                             <div className="w-4 h-4 border-t-2 border-blue-400 rounded-full animate-spin"></div>
                             <span>Getting detailed AI analysis...</span>
                         </div>
                    )}
                    
                    {error && (
                        <div className="p-3 mb-3 text-sm text-red-300 bg-red-500/10 border border-red-500/20 rounded">{error}</div>
                    )}

                    {/* Basic Detection Results */}
                    {detectionResult && !detailedAnalysis && (
                        <div key={detectionResult.message} className={`p-4 rounded-lg ${
                            detectionResult.duplicate
                                ? 'bg-blue-500/10 border border-blue-500/20 text-blue-200'
                                : (isSuccess ? 'bg-green-500/10 border border-green-500/20 text-green-200' : (isDetected ? 'bg-yellow-500/10 border border-yellow-500/20 text-yellow-200' : 'bg-red-500/10 border border-red-500/20 text-red-200'))
                        }`}>
                            <div className="flex items-center justify-between">
                                <p className="font-bold text-lg">
                                    {detectionResult.duplicate
                                        ? 'Already Detected'
                                        : (inputType === 'photo' 
                                            ? (isSuccess ? 'Waste Detected: Points Earned!' : isDetected ? 'Waste Detected: No Points' : 'Not Detected')
                                            : (isSuccess ? 'Disposal Verified: Points Earned!' : 'Disposal Not Verified'))
                                        }
                                </p>
                                {typeof detectionResult.awarded_points === 'number' && (
                                    <span className="px-3 py-1 rounded-full bg-white/10 border border-white/20 text-sm">
                                        +{detectionResult.awarded_points} pts
                                    </span>
                                )}
                            </div>
                            <p className="text-sm mt-1">{detectionResult.message}</p>
                            
                            {/* Video Analysis Results */}
                            {inputType !== 'photo' && detectionResult.video_analysis && (
                                <div className="mt-3 p-3 bg-white/5 border border-white/10 rounded">
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className="text-lg">🎥</span>
                                        <span className="font-medium text-sm">Video Analysis</span>
                                    </div>
                                    <div className="text-xs space-y-1">
                                        <div className="flex justify-between">
                                            <span className="text-gray-400">Waste Type:</span>
                                            <span className="text-gray-200">{detectionResult.video_analysis.waste_type || 'Unknown'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-gray-400">Disposal Verified:</span>
                                            <span className={`font-medium ${detectionResult.video_analysis.disposal_verified ? 'text-green-400' : 'text-red-400'}`}>
                                                {detectionResult.video_analysis.disposal_verified ? 'Yes' : 'No'}
                                            </span>
                                        </div>
                                        {detectionResult.video_analysis.reasoning && (
                                            <div className="mt-2 pt-2 border-t border-white/10">
                                                <span className="text-gray-400 text-xs">AI Reasoning:</span>
                                                <p className="text-gray-300 text-xs mt-1 leading-relaxed">
                                                    {detectionResult.video_analysis.reasoning}
                                                </p>
                                            </div>
                                        )}
                                        {!detectionResult.video_analysis.disposal_verified && (
                                            <div className="mt-2 pt-2 border-t border-white/10">
                                                <span className="text-gray-400 text-xs">💡 Tips for better detection:</span>
                                                <ul className="text-gray-300 text-xs mt-1 space-y-1">
                                                    <li>• Ensure the waste item is clearly visible in your hand</li>
                                                    <li>• Show the disposal action clearly (item going into bin)</li>
                                                    <li>• Keep the video steady and well-lit</li>
                                                    <li>• Record for at least 2-3 seconds</li>
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Quick Summary */}
                            {(detectionResult.recyclable_items?.length || detectionResult.hazardous_items?.length || detectionResult.general_items?.length) && (
                                <div className="mt-3">
                                    <div className="text-xs text-gray-400 border-b border-white/10 pb-2 mb-3">
                                        <span className="inline-flex items-center gap-1">
                                            <span className={`w-2 h-2 rounded-full ${
                                                detectionResult.gemini_analysis?.available 
                                                    ? 'bg-green-400' 
                                                    : detectionResult.gemini_analysis?.fallback 
                                                        ? 'bg-yellow-400' 
                                                        : 'bg-red-400'
                                            }`}></span>
                                            Detected With AI {
                                                detectionResult.gemini_analysis?.available 
                                                    ? 'Active' 
                                                    : detectionResult.gemini_analysis?.fallback 
                                                        ? 'Fallback' 
                                                        : 'Unavailable'
                                            }
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                        {detectionResult.recyclable_items?.length > 0 && (
                                            <div className="text-center p-2 bg-eco-green/10 border border-eco-green/20 rounded">
                                                <div className="text-2xl mb-1">♻️</div>
                                                <div className="text-xs text-eco-green font-medium">{detectionResult.recyclable_items.length} Recyclable</div>
                                            </div>
                                        )}
                                        {detectionResult.hazardous_items?.length > 0 && (
                                            <div className="text-center p-2 bg-yellow-500/10 border border-yellow-500/20 rounded">
                                                <div className="text-2xl mb-1">⚠️</div>
                                                <div className="text-xs text-yellow-300 font-medium">{detectionResult.hazardous_items.length} Hazardous</div>
                                            </div>
                                        )}
                                        {detectionResult.general_items?.length > 0 && (
                                            <div className="text-center p-2 bg-gray-500/10 border border-gray-500/20 rounded">
                                                <div className="text-2xl mb-1">🗑️</div>
                                                <div className="text-xs text-gray-300 font-medium">{detectionResult.general_items.length} General</div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Detailed Analysis Results */}
                    {detailedAnalysis && (
                        <div className="space-y-4">
                            {/* Analysis Header */}
                            <div className="p-4 bg-gradient-to-r from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-lg">
                                <div className="flex items-center justify-between mb-2">
                                    <h3 className="text-lg font-bold text-blue-200 flex items-center gap-2">
                                        {inputType === 'photo' ? '🧠 AI Waste Analysis' : '🎥 AI Video Analysis'}
                                    </h3>
                                    <div className="flex items-center gap-2">
                                        <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-full border border-green-500/30">
                                        Detected With AI
                                        </span>
                                        {detailedAnalysis.potential_points > 0 && (
                                            <span className="px-2 py-1 bg-eco-green/20 text-eco-green text-xs rounded-full border border-eco-green/30">
                                                +{detailedAnalysis.potential_points} pts
                                            </span>
                                        )}
                                    </div>
                                </div>
                                
                                {inputType === 'photo' && detailedAnalysis.summary && (
                                    <p className="text-sm text-gray-300 leading-relaxed">{detailedAnalysis.summary}</p>
                                )}
                                
                                {inputType !== 'photo' && detailedAnalysis.video_analysis && (
                                    <div className="space-y-2">
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm text-gray-400">Waste Type:</span>
                                            <span className="text-sm text-gray-200 font-medium">{detailedAnalysis.waste_type || 'Unknown'}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-sm text-gray-400">Disposal Verified:</span>
                                            <span className={`text-sm font-medium ${detailedAnalysis.disposal_verified ? 'text-green-400' : 'text-red-400'}`}>
                                                {detailedAnalysis.disposal_verified ? 'Yes' : 'No'}
                                            </span>
                                        </div>
                                        {detailedAnalysis.reasoning && (
                                            <div className="mt-3 p-3 bg-white/5 border border-white/10 rounded">
                                                <span className="text-sm text-gray-400 font-medium">AI Analysis Reasoning:</span>
                                                <p className="text-sm text-gray-300 mt-1 leading-relaxed">
                                                    {detailedAnalysis.reasoning}
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Waste Items Analysis - Only for photos */}
                            {inputType === 'photo' && detailedAnalysis.analysis?.items?.length > 0 && (
                                <div className="space-y-3">
                                    <h4 className="text-md font-semibold text-gray-200 flex items-center gap-2">
                                        📋 Detected Items
                                    </h4>
                                    
                                    {detailedAnalysis.analysis.items.map((item, idx) => {
                                        const isExpanded = expandedItems.has(idx);
                                        const categoryColors = {
                                            recyclable: 'border-eco-green/30 bg-eco-green/5',
                                            hazardous: 'border-yellow-500/30 bg-yellow-500/5',
                                            general: 'border-gray-500/30 bg-gray-500/5'
                                        };
                                        const categoryIcons = {
                                            recyclable: '♻️',
                                            hazardous: '⚠️',
                                            general: '🗑️'
                                        };
                                        const categoryTextColors = {
                                            recyclable: 'text-eco-green',
                                            hazardous: 'text-yellow-300',
                                            general: 'text-gray-300'
                                        };

                                        return (
                                            <div key={idx} className={`border rounded-lg p-4 transition-all duration-200 ${categoryColors[item.category] || categoryColors.general}`}>
                                                <div 
                                                    className="flex items-center justify-between cursor-pointer"
                                                    onClick={() => toggleItemExpansion(idx)}
                                                >
                                                    <div className="flex items-center gap-3">
                                                        <span className="text-2xl">{categoryIcons[item.category] || '🗑️'}</span>
                                                        <div>
                                                            <h5 className={`font-semibold ${categoryTextColors[item.category] || categoryTextColors.general}`}>
                                                                {item.name}
                                                            </h5>
                                                            <p className="text-xs text-gray-400 capitalize">{item.category} waste</p>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <span className={`px-2 py-1 text-xs rounded-full border ${
                                                            item.category === 'recyclable' ? 'bg-eco-green/20 text-eco-green border-eco-green/30' :
                                                            item.category === 'hazardous' ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' :
                                                            'bg-gray-500/20 text-gray-300 border-gray-500/30'
                                                        }`}>
                                                            {item.category}
                                                        </span>
                                                        <span className="text-gray-400 text-lg transition-transform duration-200" style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
                                                            ▼
                                                        </span>
                                                    </div>
                                                </div>

                                                {isExpanded && (
                                                    <div className="mt-4 pt-4 border-t border-white/10 space-y-3">
                                                        {item.description && (
                                                            <div>
                                                                <h6 className="text-sm font-medium text-gray-200 mb-1">Description</h6>
                                                                <p className="text-sm text-gray-300">{item.description}</p>
                                                            </div>
                                                        )}
                                                        
                                                        {item.disposal_tip && (
                                                            <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded">
                                                                <h6 className="text-sm font-medium text-blue-200 mb-1 flex items-center gap-1">
                                                                    💡 Disposal Instructions
                                                                </h6>
                                                                <p className="text-sm text-gray-300">{item.disposal_tip}</p>
                                                            </div>
                                                        )}
                                                        
                                                        {item.environmental_impact && (
                                                            <div className="p-3 bg-green-500/10 border border-green-500/20 rounded">
                                                                <h6 className="text-sm font-medium text-green-200 mb-1 flex items-center gap-1">
                                                                    🌱 Environmental Impact
                                                                </h6>
                                                                <p className="text-sm text-gray-300">{item.environmental_impact}</p>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {/* Environmental Tips - Only for photos */}
                            {inputType === 'photo' && detailedAnalysis.disposal_tips?.length > 0 && (
                                <div className="p-4 bg-green-500/5 border border-green-500/20 rounded-lg">
                                    <h4 className="text-md font-semibold text-green-200 mb-3 flex items-center gap-2">
                                        🌱 Environmental Tips
                                    </h4>
                                    <div className="space-y-2">
                                        {detailedAnalysis.disposal_tips.map((tip, idx) => (
                                            <div key={idx} className="flex items-start gap-2 text-sm text-gray-300">
                                                <span className="text-green-400 mt-0.5">•</span>
                                                <span>{tip}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default EarnPoints;