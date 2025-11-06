import json
import os
import urllib.request
import urllib.parse
from urllib.error import HTTPError
import boto3
import re
import html # For escaping

# --- Initialize Services ---
try:
    dynamodb = boto3.resource('dynamodb')
    USER_TABLE_NAME = 'VoiceRecipeAssistant-Users'
    user_table = dynamodb.Table(USER_TABLE_NAME)
    print("DynamoDB connected.")
except Exception as e:
    print(f"ERROR connecting DynamoDB: {e}"); user_table = None

API_HOST = "https://api.spoonacular.com"
SEARCH_PATH = "/recipes/findByIngredients"
INSTRUCTIONS_PATH = "/recipes/{id}/analyzedInstructions"
NUTRITION_PATH = "/recipes/{id}/nutritionWidget.json"

NON_VEGAN_KEYWORDS = ['beef', 'pork', 'lamb', 'chicken', 'turkey', 'fish', 'salmon', 'tuna', 'shrimp', 'cheese', 'milk', 'yogurt', 'butter', 'cream', 'paneer', 'egg', 'honey']
NON_VEGAN_PATTERN = re.compile(r'\b(?:' + '|'.join(NON_VEGAN_KEYWORDS) + r')\b', re.IGNORECASE)

def escape_ssml(text):
    """ Escapes characters invalid in SSML using html.escape """
    return html.escape(text or "", quote=True)

# ================= ROUTER =====================
def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")
    # Safely get intent name, handle potential missing keys
    intent_name = event.get('sessionState', {}).get('intent', {}).get('name', 'FallbackIntent')
    print(f"Intent: {intent_name}")

    if intent_name == 'UpdateProfile': return handle_update_profile(event)
    elif intent_name == 'SearchRecipes': return handle_search_recipes(event)
    elif intent_name == 'StartCooking': return handle_start_cooking(event)
    elif intent_name == 'NextStep': return handle_next_step(event)
    elif intent_name == 'GetNutrition': return handle_get_nutrition(event)
    else: # Default to FallbackIntent
        ssml_msg = f"<speak>Sorry, I'm not sure how to handle that command.</speak>"
        return build_lex_response({},'FallbackIntent', {"ssmlMessage": ssml_msg}, "SSML")


# ================= SEARCH RECIPES ==================
def handle_search_recipes(event):
    print("Handler: search_recipes")
    try: API_KEY = os.environ['SPOONACULAR_API_KEY']
    except KeyError: return build_lex_response({}, "SearchRecipes", {"ssmlMessage": "<speak>Assistant not configured: Missing API key.</speak>"}, "SSML")

    session_attrs = event.get('sessionState', {}).get('sessionAttributes', {})
    user_id = event.get('sessionId', 'test-user'); user_profile = get_user_profile(user_id)
    intent_name = event['sessionState']['intent']['name']; slots = event['sessionState']['intent']['slots']

    # --- Robust Ingredient Extraction ---
    ingredients = []
    ingredient_slot = slots.get('Ingredient') # Get the slot safely
    if ingredient_slot:
        if 'values' in ingredient_slot and ingredient_slot['values']: # Check if values list exists and is not empty
            ingredients.extend(v['value']['interpretedValue'] for v in ingredient_slot['values'] if v.get('value') and v['value'].get('interpretedValue'))
        elif 'value' in ingredient_slot and ingredient_slot['value'] and ingredient_slot['value'].get('interpretedValue'): # Check if single value exists
             ingredients.append(ingredient_slot['value']['interpretedValue'])

    # --- Check for ingredients AFTER attempting extraction ---
    if not ingredients:
        print("No valid ingredients found in slots.")
        return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>I didn't catch any valid ingredients. Please try again.</speak>"}, "SSML")
    # --- End Check ---

    ingredients_str = ",".join(ingredients)
    print(f"Found ingredients: {ingredients_str}")

    params = {"apiKey": API_KEY, "ingredients": ingredients_str, "number": 10, "ranking": 1}
    user_diet = user_profile.get('diet'); allergies = set(user_profile.get('allergies', [])); is_vegan = False
    if user_diet:
        if user_diet.lower() == 'vegan': is_vegan = True; allergies.update(["dairy", "eggs"])
        else: params['diet'] = user_diet
    if allergies: params['intolerances'] = ",".join(list(allergies))
    url = f"{API_HOST}{SEARCH_PATH}?{urllib.parse.urlencode(params)}"
    print(f"API Call: {url}")
    try:
        req = urllib.request.Request(url);
        with urllib.request.urlopen(req) as resp: api_recipes = json.loads(resp.read().decode('utf-8'))
        recipes = [r for r in api_recipes if not (is_vegan and NON_VEGAN_PATTERN.search(r.get('title','')))] if is_vegan else api_recipes
        if not recipes:
            filter_msg_text = f" for your {user_diet} diet" if user_diet else ""; filter_msg_text += f" avoiding {','.join(list(allergies))}" if allergies else ""
            plain_msg = f"Sorry, I couldn't find recipes matching {ingredients_str}{filter_msg_text}."
            ssml_msg = f"<speak>{escape_ssml(plain_msg)}</speak>"
            msg = {"ssmlMessage": ssml_msg}; session_attrs = {}
        else:
            top_recipe = recipes[0]; recipe_id, title, img = str(top_recipe['id']), top_recipe['title'], top_recipe.get('image', '')
            session_attrs.update({'currentRecipeId': recipe_id, 'currentRecipeTitle': title}); session_attrs.pop('cookingSteps', None); session_attrs.pop('currentStep', None)
            filter_msg_text = f" for your {user_diet} diet" if user_diet else ""; filter_msg_text += f" avoiding {','.join(list(allergies))}" if allergies else ""
            plain_msg = f"Success! I found {len(recipes[:1])} valid recipe(s){filter_msg_text}. The top result is {title}. You can ask me to 'start cooking' or 'get nutrition'."
            ssml_msg = f"<speak>{escape_ssml(plain_msg)}</speak>"
            msg = {"ssmlMessage": ssml_msg, "recipeInfo": {"title": title, "imageUrl": img}}
    except HTTPError as e:
        print(f"API Error: {e.code}");
        error_detail = ""
        try: # Try to read error body for more info
           error_body = e.read().decode('utf-8')
           print(f"API Error Body: {error_body}")
           if e.code == 401: error_detail = " Check the API key."
           elif e.code == 402: error_detail = " The API quota might be exceeded."
        except Exception: pass # Ignore if reading body fails
        msg = {"ssmlMessage": f"<speak>Sorry, there was an error searching for recipes.{error_detail}</speak>"};
        session_attrs = {}
    except Exception as e:
        print(f"Search Exception: {str(e)}")
        msg = {"ssmlMessage": "<speak>Sorry, an unexpected problem occurred while searching.</speak>"};
        session_attrs = {}

    return build_lex_response(session_attrs, intent_name, msg, "SSML", "Close") # Send SSML


# ================= START COOKING ===================
def handle_start_cooking(event):
    print("Handler: start_cooking")
    session_attrs = event.get('sessionState', {}).get('sessionAttributes', {})
    recipe_id = session_attrs.get('currentRecipeId'); title = session_attrs.get('currentRecipeTitle', 'recipe')
    if not recipe_id: return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": "<speak>No recipe loaded.</speak>"}, "SSML")
    try:
        API_KEY = os.environ['SPOONACULAR_API_KEY']; url = f"{API_HOST}{INSTRUCTIONS_PATH.format(id=recipe_id)}?apiKey={API_KEY}"
        print(f"Fetching instructions: {url}"); req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp: instructions = json.loads(resp.read().decode('utf-8'))
        if not instructions or not isinstance(instructions, list) or not instructions[0].get('steps'): return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": f"<speak>Couldn't find steps for {escape_ssml(title)}.</speak>"}, "SSML")
        steps_data = instructions[0]['steps']
        if not steps_data: return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": f"<speak>No steps listed for {escape_ssml(title)}.</speak>"}, "SSML")
        steps = [s['step'] for s in steps_data]; session_attrs.update({'cookingSteps': json.dumps(steps), 'currentStep': "0"})
        safe_title = escape_ssml(title); safe_step = escape_ssml(steps[0])
        ssml = f"<speak>OK, let's cook {safe_title}. <break time='500ms'/> Step 1: {safe_step} <break time='1s'/> Say 'next'.</speak>"
        return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": ssml}, "SSML", "ElicitIntent")
    except HTTPError as e: print(f"API Error instructions: {e.code}"); return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": "<speak>Error getting instructions from service.</speak>"}, "SSML")
    except Exception as e: print(f"Parse Error instructions: {str(e)}"); return build_lex_response(session_attrs, "StartCooking", {"ssmlMessage": "<speak>Error processing instructions.</speak>"}, "SSML")

# ================= NEXT STEP ======================
def handle_next_step(event):
    print("Handler: next_step")
    session_attrs = event.get('sessionState', {}).get('sessionAttributes', {})
    if 'cookingSteps' not in session_attrs or 'currentStep' not in session_attrs: return build_lex_response(session_attrs, "NextStep", {"ssmlMessage": "<speak>No steps loaded.</speak>"}, "SSML")
    try:
        steps = json.loads(session_attrs['cookingSteps']); current_idx = int(session_attrs['currentStep']); next_idx = current_idx + 1
        if next_idx >= len(steps):
            session_attrs = {}; ssml = "<speak>You're all done! Enjoy.</speak>"
            return build_lex_response(session_attrs, "NextStep", {"ssmlMessage": ssml}, "SSML", "Close")
        else:
            session_attrs['currentStep'] = str(next_idx)
            safe_step = escape_ssml(steps[next_idx])
            ssml = f"<speak>Step {next_idx + 1}: {safe_step} <break time='1s'/> Say 'next'.</speak>"
            return build_lex_response(session_attrs, "NextStep", {"ssmlMessage": ssml}, "SSML", "ElicitIntent")
    except Exception as e: print(f"Error in next_step: {str(e)}"); return build_lex_response(session_attrs, "NextStep", {"ssmlMessage": "<speak>Sorry, I lost my place.</speak>"}, "SSML")

# ================= UPDATE PROFILE ==================
def handle_update_profile(event):
    print("Handler: update_profile")
    session_attrs = event.get('sessionState', {}).get('sessionAttributes', {});
    if not user_table: return build_lex_response(session_attrs, "UpdateProfile", {"ssmlMessage": "<speak>Can't connect user database.</speak>"}, "SSML")
    intent_name, slots, user_id = event['sessionState']['intent']['name'], event['sessionState']['intent']['slots'], event.get('sessionId')
    if not user_id: return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>Can't find session ID.</speak>"}, "SSML")
    diet_slot, allergy_slot = slots.get('Diet'), slots.get('Allergy'); parts, vals, names, saved = [], {}, {}, []
    current_allergies = set(get_user_profile(user_id).get('allergies', [])); new_allergies = set()
    if diet_slot and diet_slot.get('value'): user_diet = diet_slot['value']['interpretedValue']; parts.append("#d = :d"); names['#d'], vals[':d'] = 'diet', user_diet; saved.append(f"diet as {user_diet}")
    if allergy_slot and allergy_slot.get('values'): new_allergies.update(v['value']['interpretedValue'] for v in allergy_slot['values'] if v.get('value') and v['value'].get('interpretedValue'))
    elif allergy_slot and allergy_slot.get('value') and allergy_slot['value'].get('interpretedValue'): new_allergies.add(allergy_slot['value']['interpretedValue'])
    if new_allergies: combined = current_allergies.union(new_allergies); parts.append("#a = :a"); names['#a'], vals[':a'] = 'allergies', list(combined); saved.append(f"allergies as {', '.join(vals[':a'])}")
    if not saved: return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>Didn't catch what profile information to save.</speak>"}, "SSML")
    try:
        user_table.update_item(Key={'UserId': user_id}, UpdateExpression="SET " + ", ".join(parts), ExpressionAttributeNames=names, ExpressionAttributeValues=vals)
        plain_msg = f"OK! Updated profile with { ' and '.join(saved) }."
    except Exception as e: print(f"DB Error: {str(e)}"); plain_msg = "Problem saving profile update."
    ssml_msg = f"<speak>{escape_ssml(plain_msg)}</speak>"
    return build_lex_response(session_attrs, intent_name, {"ssmlMessage": ssml_msg}, "SSML") # Send SSML


# ================= GET NUTRITION ===================
def handle_get_nutrition(event):
    print("Handler: get_nutrition")
    session_attrs = event.get('sessionState', {}).get('sessionAttributes', {}); intent_name = event['sessionState']['intent']['name']
    recipe_id = session_attrs.get('currentRecipeId'); title = session_attrs.get('currentRecipeTitle', 'the recipe')
    if not recipe_id: return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>No recipe loaded.</speak>"}, "SSML")
    try:
        API_KEY = os.environ['SPOONACULAR_API_KEY']; url = f"{API_HOST}{NUTRITION_PATH.format(id=recipe_id)}?apiKey={API_KEY}"
        print(f"Fetching nutrition: {url}"); req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp: nutrition = json.loads(resp.read().decode('utf-8'))
        cal, prot, fat, carb = nutrition.get('calories', 'N/A'), nutrition.get('protein', 'N/A'), nutrition.get('fat', 'N/A'), nutrition.get('carbs', 'N/A')
        plain_msg = f"Nutrition for {title} (per serving): Calories are {cal}, Protein is {prot}, Fat is {fat}, and Carbohydrates are {carb}."
        ssml_msg = f"<speak>{escape_ssml(plain_msg)}</speak>"
        return build_lex_response(session_attrs, intent_name, {"ssmlMessage": ssml_msg}, "SSML", "ElicitIntent")
    except HTTPError as e: print(f"API Error nutrition: {e.code}"); return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>Couldn't get nutrition info.</speak>"}, "SSML")
    except Exception as e: print(f"Parse Error nutrition: {str(e)}"); return build_lex_response(session_attrs, intent_name, {"ssmlMessage": "<speak>Error getting nutrition info.</speak>"}, "SSML")

# ================= HELPERS ======================
def build_lex_response(session_attrs, intent_name, msg_content, msg_type_hint="PlainText", dialog_action_type="Close"):
    final_content, content_type = "", "PlainText"
    if isinstance(msg_content, dict) and "ssmlMessage" in msg_content: final_content, content_type = msg_content["ssmlMessage"], "SSML"
    elif isinstance(msg_content, dict) and "plainTextMessage" in msg_content: final_content = msg_content["plainTextMessage"]; content_type="PlainText" # Always use PlainText if ssmlMessage not present
    elif isinstance(msg_content, str): final_content, content_type = msg_content, "PlainText" # Assume string is PlainText
    else: final_content = "<speak>Processing complete.</speak>"; content_type="SSML" # Default SSML fallback

    # If the FINAL decision is SSML, ensure it's wrapped
    if content_type == "SSML" and not final_content.strip().startswith('<speak>'):
        final_content = f"<speak>{escape_ssml(final_content)}</speak>"

    intent_state = "InProgress" if dialog_action_type != "Close" else "Fulfilled"; current_intent = {"name": intent_name, "state": intent_state, "slots": {}}
    dialog_action = {"type": dialog_action_type}
    # For Close action, Lex V2 requires intent details within dialogAction
    if dialog_action_type == "Close": dialog_action["intent"] = {"name": intent_name, "state": "Fulfilled", "slots": {}}
    safe_session_attrs = session_attrs or {}
    response = {"sessionState": {"sessionAttributes": safe_session_attrs, "dialogAction": dialog_action, "intent": current_intent}, "messages": [{"contentType": content_type, "content": final_content}]}
    if isinstance(msg_content, dict) and "recipeInfo" in msg_content:
        response['sessionState']['sessionAttributes']['appContext'] = json.dumps({"recipeInfo": msg_content["recipeInfo"]})
    print(f"Final sessionAttributes: {json.dumps(response['sessionState']['sessionAttributes'])}")
    print(f"Sending message type: {content_type}")
    return response

def get_user_profile(user_id):
    if not user_table: return {'allergies': []}
    try:
        resp = user_table.get_item(Key={'UserId': user_id})
        if 'Item' in resp: profile = resp['Item']; profile.setdefault('allergies', []); return profile
        else: print(f"No profile for {user_id}. Creating."); new_profile = {'UserId': user_id, 'allergies': []}; user_table.put_item(Item=new_profile); return new_profile
    except Exception as e: print(f"DB Error get/create profile: {str(e)}"); return {'allergies': []}