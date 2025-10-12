// src/components/WasteBounty.jsx

import React, { useState, useEffect } from 'react';

const WasteBounty = ({ currentUser, updatePoints }) => {
    const [activeTab, setActiveTab] = useState('report'); // 'report', 'bounties', 'cleanup'
    const [bounties, setBounties] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    
    // Report bounty states
    const [reportPhoto, setReportPhoto] = useState(null);
    const [reportPreview, setReportPreview] = useState(null);
    
    // Cleanup states
    const [selectedBounty, setSelectedBounty] = useState(null);
    const [beforePhoto, setBeforePhoto] = useState(null);
    const [afterPhoto, setAfterPhoto] = useState(null);
    const [beforePreview, setBeforePreview] = useState(null);
    const [afterPreview, setAfterPreview] = useState(null);
    const [cleanupStep, setCleanupStep] = useState('before'); // 'before', 'after', 'submit'

    // Load bounties on component mount
    useEffect(() => {
        if (activeTab === 'bounties') {
            loadBounties();
        }
    }, [activeTab]);

    const loadBounties = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const token = localStorage.getItem('authToken');
            const res = await fetch('http://localhost:5000/api/bounties', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Failed to load bounties');
                return;
            }
            
            setBounties(data.bounties || []);
        } catch (e) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const validateGeotag = (file) => {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const arrayBuffer = e.target.result;
                const dataView = new DataView(arrayBuffer);
                
                // Check for EXIF header
                if (dataView.getUint16(0) !== 0xFFD8) {
                    reject(new Error('Not a valid JPEG file'));
                    return;
                }
                
                let offset = 2;
                let hasGPS = false;
                
                while (offset < dataView.byteLength) {
                    const marker = dataView.getUint16(offset);
                    if (marker === 0xFFE1) { // APP1 marker (EXIF)
                        const exifLength = dataView.getUint16(offset + 2);
                        const exifData = new DataView(arrayBuffer, offset + 4, exifLength - 2);
                        
                        // Check for GPS IFD
                        if (exifData.getUint32(0) === 0x45786966) { // "Exif" string
                            hasGPS = true;
                            break;
                        }
                    }
                    offset += 2 + dataView.getUint16(offset + 2);
                }
                
                if (hasGPS) {
                    resolve(true);
                } else {
                    reject(new Error('Photo must contain GPS location data. Please enable location services and take a new photo.'));
                }
            };
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsArrayBuffer(file);
        });
    };

    const handleReportPhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            await validateGeotag(file);
            setReportPhoto(file);
            setReportPreview(URL.createObjectURL(file));
            setError(null);
        } catch (err) {
            setError(err.message);
            setReportPhoto(null);
            setReportPreview(null);
        }
    };

    const handleBeforePhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            await validateGeotag(file);
            setBeforePhoto(file);
            setBeforePreview(URL.createObjectURL(file));
            setError(null);
        } catch (err) {
            setError(err.message);
            setBeforePhoto(null);
            setBeforePreview(null);
        }
    };

    const handleAfterPhotoChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            await validateGeotag(file);
            setAfterPhoto(file);
            setAfterPreview(URL.createObjectURL(file));
            setError(null);
        } catch (err) {
            setError(err.message);
            setAfterPhoto(null);
            setAfterPreview(null);
        }
    };

    const submitBountyReport = async () => {
        if (!reportPhoto) {
            setError('Please take a photo first');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const token = localStorage.getItem('authToken');
            const formData = new FormData();
            formData.append('bounty_report_photo', reportPhoto);

            const res = await fetch('http://localhost:5000/api/create_bounty', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Failed to create bounty');
                return;
            }

            setSuccess('Bounty created successfully! Other users in your area can now claim it.');
            setReportPhoto(null);
            setReportPreview(null);
        } catch (e) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const claimBounty = (bounty) => {
        setSelectedBounty(bounty);
        setActiveTab('cleanup');
        setCleanupStep('before');
    };

    const submitCleanup = async () => {
        if (!beforePhoto || !afterPhoto) {
            setError('Please take both before and after photos');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const token = localStorage.getItem('authToken');
            const formData = new FormData();
            formData.append('bounty_id', selectedBounty.id);
            formData.append('before_cleanup_photo', beforePhoto);
            formData.append('after_cleanup_photo', afterPhoto);

            const res = await fetch('http://localhost:5000/api/verify_cleanup', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            const data = await res.json();
            if (!res.ok) {
                setError(data?.error || 'Cleanup verification failed');
                if (data.reasons) {
                    setError(data.reasons.join(', '));
                }
                return;
            }

            setSuccess(`Cleanup verified! You earned ${data.points_awarded} points!`);
            if (typeof data.total_points === 'number') {
                updatePoints(data.total_points);
            }
            
            // Reset cleanup state
            setSelectedBounty(null);
            setBeforePhoto(null);
            setAfterPhoto(null);
            setBeforePreview(null);
            setAfterPreview(null);
            setCleanupStep('before');
            setActiveTab('bounties');
            loadBounties(); // Refresh bounties list
        } catch (e) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-100">🗺️ Waste Bounty System</h2>
                <div className="text-sm text-gray-400">
                    Earn points by cleaning up reported waste spots
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex space-x-1 bg-white/5 p-1 rounded-lg">
                <button
                    onClick={() => setActiveTab('report')}
                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'report'
                            ? 'bg-eco-green text-white'
                            : 'text-gray-400 hover:text-gray-200'
                    }`}
                >
                    📸 Report Waste
                </button>
                <button
                    onClick={() => setActiveTab('bounties')}
                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                        activeTab === 'bounties'
                            ? 'bg-eco-green text-white'
                            : 'text-gray-400 hover:text-gray-200'
                    }`}
                >
                    🎯 Active Bounties
                </button>
                {selectedBounty && (
                    <button
                        onClick={() => setActiveTab('cleanup')}
                        className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${
                            activeTab === 'cleanup'
                                ? 'bg-eco-accent text-eco-dark'
                                : 'text-gray-400 hover:text-gray-200'
                        }`}
                    >
                        🧹 Cleanup
                    </button>
                )}
            </div>

            {/* Error/Success Messages */}
            {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-300">
                    {error}
                </div>
            )}
            {success && (
                <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-green-300">
                    {success}
                </div>
            )}

            {/* Report Waste Tab */}
            {activeTab === 'report' && (
                <div className="space-y-6">
                    <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                        <h3 className="text-lg font-semibold text-gray-100 mb-4">Report a Public Waste Spot</h3>
                        <p className="text-gray-400 text-sm mb-4">
                            Take a photo of waste in a public area. The photo must contain GPS location data.
                        </p>
                        
                        <div className="space-y-4">
                            <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-8 text-center">
                                <input
                                    type="file"
                                    accept="image/*"
                                    capture="environment"
                                    onChange={handleReportPhotoChange}
                                    className="hidden"
                                    id="report-photo-upload"
                                />
                                <label htmlFor="report-photo-upload" className="cursor-pointer">
                                    <div className="text-4xl mb-2">📸</div>
                                    <p className="text-gray-300 font-medium">Take Photo with Camera</p>
                                    <p className="text-sm text-gray-400 mt-1">GPS location required</p>
                                    {reportPhoto && (
                                        <p className="text-sm text-eco-green mt-2 font-semibold">
                                            Photo captured: {reportPhoto.name}
                                        </p>
                                    )}
                                </label>
                            </div>

                            {reportPreview && (
                                <div className="space-y-2">
                                    <p className="text-sm text-gray-300">Preview:</p>
                                    <img
                                        src={reportPreview}
                                        alt="Report preview"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                </div>
                            )}

                            <button
                                onClick={submitBountyReport}
                                disabled={!reportPhoto || loading}
                                className={`w-full py-3 px-4 rounded-lg font-semibold transition-colors ${
                                    !reportPhoto || loading
                                        ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed'
                                        : 'bg-eco-green text-white hover:brightness-110'
                                }`}
                            >
                                {loading ? 'Creating Bounty...' : 'Create Bounty (+200 pts)'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Active Bounties Tab */}
            {activeTab === 'bounties' && (
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-lg font-semibold text-gray-100">Available Bounties in Your Area</h3>
                        <button
                            onClick={loadBounties}
                            disabled={loading}
                            className="px-3 py-1 text-sm bg-white/10 text-gray-300 rounded-md hover:bg-white/20 transition-colors"
                        >
                            {loading ? 'Loading...' : 'Refresh'}
                        </button>
                    </div>

                    {bounties.length === 0 ? (
                        <div className="text-center py-8 text-gray-400">
                            <div className="text-4xl mb-2">🎯</div>
                            <p>No active bounties in your area</p>
                            <p className="text-sm mt-1">Be the first to report waste spots!</p>
                        </div>
                    ) : (
                        <div className="grid gap-4">
                            {bounties.map((bounty) => (
                                <div key={bounty.id} className="bg-white/5 border border-white/10 rounded-lg p-4">
                                    <div className="flex items-start justify-between">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2 mb-2">
                                                <span className="text-2xl">🗑️</span>
                                                <div>
                                                    <p className="font-semibold text-gray-100">
                                                        Bounty #{bounty.id}
                                                    </p>
                                                    <p className="text-sm text-gray-400">
                                                        {bounty.city}, {bounty.state}
                                                    </p>
                                                </div>
                                            </div>
                                            <p className="text-sm text-gray-300 mb-2">
                                                Reported: {new Date(bounty.created_at).toLocaleDateString()}
                                            </p>
                                            <div className="flex items-center gap-4 text-sm">
                                                <span className="text-eco-green font-semibold">
                                                    +{bounty.bounty_points} pts
                                                </span>
                                                <span className="text-gray-400">
                                                    📍 {bounty.latitude.toFixed(4)}, {bounty.longitude.toFixed(4)}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="ml-4">
                                            <img
                                                src={`http://localhost:5000${bounty.waste_image_url}`}
                                                alt="Waste spot"
                                                className="w-20 h-20 object-cover rounded-lg"
                                            />
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => claimBounty(bounty)}
                                        className="w-full mt-3 py-2 bg-eco-accent text-eco-dark font-semibold rounded-lg hover:brightness-110 transition-colors"
                                    >
                                        Claim & Submit Cleanup Photos
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Cleanup Tab */}
            {activeTab === 'cleanup' && selectedBounty && (
                <div className="space-y-6">
                    <div className="bg-white/5 border border-white/10 rounded-xl p-6">
                        <h3 className="text-lg font-semibold text-gray-100 mb-4">
                            Cleanup: Bounty #{selectedBounty.id}
                        </h3>
                        <p className="text-gray-400 text-sm mb-4">
                            Take two photos: one before cleanup and one after. Both must contain GPS location data.
                        </p>

                        <div className="space-y-6">
                            {/* Before Cleanup Photo */}
                            <div className="space-y-3">
                                <h4 className="font-medium text-gray-200 flex items-center gap-2">
                                    <span className="text-2xl">📷</span>
                                    Before Cleanup Photo
                                </h4>
                                <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-6 text-center">
                                    <input
                                        type="file"
                                        accept="image/*"
                                        capture="environment"
                                        onChange={handleBeforePhotoChange}
                                        className="hidden"
                                        id="before-photo-upload"
                                    />
                                    <label htmlFor="before-photo-upload" className="cursor-pointer">
                                        <div className="text-3xl mb-2">📸</div>
                                        <p className="text-gray-300 font-medium">Take Before Photo</p>
                                        <p className="text-sm text-gray-400 mt-1">Show the waste before cleaning</p>
                                        {beforePhoto && (
                                            <p className="text-sm text-eco-green mt-2 font-semibold">
                                                Photo captured: {beforePhoto.name}
                                            </p>
                                        )}
                                    </label>
                                </div>
                                {beforePreview && (
                                    <img
                                        src={beforePreview}
                                        alt="Before cleanup"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                )}
                            </div>

                            {/* After Cleanup Photo */}
                            <div className="space-y-3">
                                <h4 className="font-medium text-gray-200 flex items-center gap-2">
                                    <span className="text-2xl">✅</span>
                                    After Cleanup Photo
                                </h4>
                                <div className="border-2 border-dashed border-white/20 bg-white/5 rounded-lg p-6 text-center">
                                    <input
                                        type="file"
                                        accept="image/*"
                                        capture="environment"
                                        onChange={handleAfterPhotoChange}
                                        className="hidden"
                                        id="after-photo-upload"
                                    />
                                    <label htmlFor="after-photo-upload" className="cursor-pointer">
                                        <div className="text-3xl mb-2">📸</div>
                                        <p className="text-gray-300 font-medium">Take After Photo</p>
                                        <p className="text-sm text-gray-400 mt-1">Show the area after cleaning</p>
                                        {afterPhoto && (
                                            <p className="text-sm text-eco-green mt-2 font-semibold">
                                                Photo captured: {afterPhoto.name}
                                            </p>
                                        )}
                                    </label>
                                </div>
                                {afterPreview && (
                                    <img
                                        src={afterPreview}
                                        alt="After cleanup"
                                        className="w-full max-w-md mx-auto rounded-lg shadow-md"
                                    />
                                )}
                            </div>

                            <button
                                onClick={submitCleanup}
                                disabled={!beforePhoto || !afterPhoto || loading}
                                className={`w-full py-3 px-4 rounded-lg font-semibold transition-colors ${
                                    !beforePhoto || !afterPhoto || loading
                                        ? 'bg-gray-500/40 text-gray-300 cursor-not-allowed'
                                        : 'bg-eco-accent text-eco-dark hover:brightness-110'
                                }`}
                            >
                                {loading ? 'Verifying Cleanup...' : `Submit Cleanup (+${selectedBounty.bounty_points} pts)`}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default WasteBounty;
