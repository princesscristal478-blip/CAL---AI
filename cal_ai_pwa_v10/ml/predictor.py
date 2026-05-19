def predict_calories(age, weight, height, gender, activity, goal):
    """Mifflin-St Jeor BMR → TDEE with macro breakdown."""
    if gender == 'male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    af = {'sedentary':1.2,'light':1.375,'moderate':1.55,'active':1.725,'very_active':1.9}
    tdee = bmr * af.get(activity, 1.55)

    if goal == 'lose': tdee -= 500
    elif goal == 'gain': tdee += 500

    tdee = round(tdee)
    bmi = round(weight / ((height / 100) ** 2), 1)

    if bmi < 18.5: bmi_cat = "Underweight"
    elif bmi < 25: bmi_cat = "Normal weight"
    elif bmi < 30: bmi_cat = "Overweight"
    else: bmi_cat = "Obese"

    splits = {'lose':(.35,.40,.25),'maintain':(.25,.50,.25),'gain':(.30,.50,.20)}
    p, c, f = splits.get(goal, (.25,.50,.25))

    return {
        'calories': tdee, 'bmr': round(bmr), 'bmi': bmi,
        'bmi_category': bmi_cat,
        'protein_g': round(tdee * p / 4),
        'carbs_g':   round(tdee * c / 4),
        'fat_g':     round(tdee * f / 9),
        'goal': goal, 'activity': activity,
    }

def get_food_suggestions(user_id):
    try:
        from database.db import get_db
        db = get_db()
        with db.cursor() as cur:
            cur.execute('''
                SELECT f.id, f.name, f.calories, f.category, COUNT(*) as freq
                FROM food_logs fl JOIN foods f ON fl.food_id = f.id
                WHERE fl.user_id = %s GROUP BY f.id ORDER BY freq DESC LIMIT 5
            ''', (user_id,))
            top = cur.fetchall()
        if top: return list(top)
        with db.cursor() as cur:
            cur.execute('''SELECT id, name, calories, category FROM foods
                           WHERE category IN ('Fruits','Vegetables','Protein')
                           ORDER BY RAND() LIMIT 5''')
            return cur.fetchall()
    except:
        return []
