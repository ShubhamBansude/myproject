const express = require('express');
const bodyParser = require('body-parser');
const mongoose = require('mongoose');
const bcrypt = require('bcrypt'); // ✅ Added bcrypt import

const app = express();
app.use(bodyParser.json());
const PORT = 5000;

// MongoDB connection
mongoose.connect("mongodb://localhost:27017/testdb", {
    useNewUrlParser: true,
    useUnifiedTopology: true
})
    .then(() => console.log('Connected to MongoDB'))
    .catch(err => console.error('Could not connect to MongoDB...', err)); // ✅ Fixed variable name

// Schema
const userSchema = new mongoose.Schema({
    uname: { type: String, unique: true, required: true },
    password: { type: String, required: true }
});

const User = mongoose.model('Users', userSchema);

// Register route
app.post('/users', async (req, res) => {
    try {
        const { uname, password } = req.body;

        const existingUser = await User.findOne({ uname });
        if (existingUser) {
            return res.status(400).json({ error: 'Username already exists' });
        }

        const hashedPassword = await bcrypt.hash(password, 10);
        const newUser = new User({ uname, password: hashedPassword });
        const savedUser = await newUser.save();

        res.status(201).json({ _id: savedUser._id, uname: savedUser.uname });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Login route
app.post('/login', async (req, res) => {
    try {
        const { uname, password } = req.body;

        const user = await User.findOne({ uname });
        if (!user) {
            return res.status(400).json({ error: 'Invalid username or password' });
        }

        const isMatch = await bcrypt.compare(password, user.password);
        if (!isMatch) {
            return res.status(400).json({ error: 'Invalid username or password' });
        }

        res.status(200).json({ message: 'Login successful', uname: user.uname });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Get all users
app.get('/users', async (req, res) => {
    try {
        const users = await User.find({}, { password: 0 });
        res.json(users);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Start server
app.listen(PORT, () => {
    console.log(`Server is Running on http://localhost:${PORT}`);
});
