// Fill these in from: Firebase Console -> Project settings -> General ->
// "Your apps" -> add a Web app -> SDK setup and configuration -> Config.
//
// These values are public client identifiers, safe to commit - they are
// NOT secrets (unlike the service-account JSON used on the Pi, which must
// never be committed or pasted anywhere). Access control here is enforced
// entirely by firestore.rules, not by hiding this file.
export const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID",
};
