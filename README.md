# aws-serverless-voice-recipe-assistant
<img width="574" height="301" alt="image" src="https://github.com/user-attachments/assets/ef70cbeb-eeb9-4f47-9dcf-f9c6e2a6f715" />
<img width="562" height="304" alt="image" src="https://github.com/user-attachments/assets/f4322334-fb1b-4802-80b9-bd5b6dbf01fe" />
<img width="579" height="336" alt="image" src="https://github.com/user-attachments/assets/70fb1fd2-7e79-4bdc-b3e4-6f8e46181ab8" />
<img width="589" height="400" alt="image" src="https://github.com/user-attachments/assets/f2d07083-6d10-4dcb-b93e-065dcd2f94a5" />

A serverless chatbot (using Amazon Lex, Lambda, Polly, and S3) that finds recipes, manages dietary profiles, and provides step-by-step voice instructions.
A serverless, conversational AI kitchen helper built as a part of the Cloud Computing course at SVKM's NMIMS, Hyderabad.

Live Demo Link: https://youtu.be/i89wo1gTGls

📖 About This Project
The Voice Recipe Assistant is a smart chatbot that helps users find recipes matching their specific dietary needs, get nutritional information, and receive voice-guided, step-by-step cooking instructions.

This application is 100% serverless, designed to be highly scalable, cost-effective, and resilient. It uses a combination of AWS AI, compute, and storage services to create a seamless user experience. 


✨ Key Features

User Personalization: The bot can understand and save user dietary preferences (e.g., vegetarian, vegan, gluten-free) and allergies (e.g., peanut-free). 

Smart Recipe Search: Connects to the Spoonacular API to dynamically search a database of 300,000+ recipes, filtering the results based on the user's saved profile. 

Voice & Visual Feedback: Every bot response is provided in both text and a real-time, natural-sounding voice using Amazon Polly. 

Stateful Cooking Mode: A StartCooking intent guides the user through the recipe one step at a time, with the user saying "next" to proceed.

Rich Content Display: The interface shows relevant recipe images and data returned from the API.

🏗️ Architecture
The entire application is event-driven and "stitched together" from managed services.
<img width="754" height="515" alt="image" src="https://github.com/user-attachments/assets/b7a13705-e2c0-405e-a307-205fb0a7971f" />

Workflow:

User (S3 & Cognito): The user visits the static website hosted in Amazon S3. Amazon Cognito provides secure, temporary credentials to the browser. 
Request (Amazon Lex): The user types a message. The browser sends this text directly to Amazon Lex V2, which uses Natural Language Understanding (NLU) to identify the user's intent. 

Logic (AWS Lambda): Lex triggers an AWS Lambda function for fulfillment. 
Data (Spoonacular API): The Lambda function (written in Python) makes a secure API call to the Spoonacular API, passing along the user's ingredients and dietary filters. 

Response (Lex & Polly):

Lambda formats the data (recipe title, image, steps) and sends it back to Lex.
Lex passes this response to the browser to display the text and image. 
The browser sends the text to Amazon Polly, which generates a lifelike audio stream that plays automatically.

🛠️ How to Set Up (For Developers)
This project relies on several cloud services and one external API.

Spoonacular API:
Create an account at Spoonacular.com to get a free API key.

AWS Lambda (/lambda/lambda_function.py):

Deploy the Python code to a new AWS Lambda function.
IMPORTANT: Do NOT paste your API key into the code. Go to Configuration > Environment Variables in your Lambda function and add a new variable:
Key: SPOONACULAR_API_KEY
Value: [Your Spoonacular API Key] 

AWS Lex:

Create a new Lex V2 bot.
Create the intents (SearchRecipes, GetNutrition, UpdateProfile, StartCooking, NextStep) and any custom slot types (like DietTypeSlot) as shown in the project report. 
In the "Fulfillment" section for each intent, point it to your new Lambda function.

Amazon Cognito:

Create a new Cognito Identity Pool and allow access for unauthenticated guest users.
Modify the Identity Pool's IAM role to grant it permission to invoke Amazon Lex and Amazon Polly.

Frontend (/frontend/):

Open script.js and update the global variables with your new Cognito Identity Pool ID and Lex Bot ID / Alias.

Amazon S3:

Upload the entire /frontend folder to an S3 bucket.
Enable Static website hosting in the bucket's properties.
Make the bucket public (or configure a public-read bucket policy). 

🙏 Acknowledgements
This project was completed as part of the Cloud Computing course at SVKM's NMIMS, Hyderabad. I would like to extend my sincere gratitude to my professor, Dr. Naresh Vurukonda, for his valuable guidance and support throughout this project
