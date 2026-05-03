THRESHOLD = 0.5


from deepface import DeepFace
import base64
import numpy as np
import cv2
import os


from .models import Person, Attendance, Subject
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from django.http import JsonResponse
from .models import Attendance
from django.http import HttpResponse

from datetime import datetime
from django.db.models import Count
from collections import defaultdict


from django.utils.timezone import localdate, localtime ,now
from .models import Attendance, Person, Subject


@csrf_exempt
def recognize(request):
    if request.method == "POST":
        data = request.POST.get("image")
        # status = request.POST.get("status", "IN")
        subject_name = request.POST.get("subject")

        # Convert base64 → image
        img_data = base64.b64decode(data)
        np_arr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # 🔍 Detect faces and select the most prominent one (largest area)
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            # 🔽 Sort faces by size (largest first)
            faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)

            if len(faces) == 0:
                return JsonResponse({"message": "No face detected", "status": "failed"})

            # Select the largest face (most prominent)
            best_face = faces[0]
            x, y, w, h = best_face

            # Crop only the selected face
            img = img[y:y+h, x:x+w]

        except Exception:
            return JsonResponse({"message": "Face detection error", "status": "failed"})

        db_path = os.path.join(settings.BASE_DIR, "ImagesAttendance")

        try:
            # 🔁 Write temp image (DeepFace is more stable with file paths)
            temp_path = os.path.join(settings.BASE_DIR, "temp_recognition.jpg")
            cv2.imwrite(temp_path, img)

            dfs = DeepFace.find(
                img_path=temp_path,
                db_path=db_path,
                enforce_detection=False,
                model_name="Facenet512",
                distance_metric="cosine",
                refresh_database=True   # Important to ensure we have the latest images for recognition
            )

            print("DFS RAW:", dfs)

            # Safe guard: no match found
            if not dfs or len(dfs) == 0 or dfs[0].empty:
                return JsonResponse({"message": "No match found in dataset", "status": "failed"})

            df = dfs[0]
            best_match = df.iloc[0]
            distance = best_match['distance']
            identity_path = best_match['identity']

            print("Best distance:", distance)

            # Threshold check (STRICT CONTROL)
            if distance >= THRESHOLD:
                return JsonResponse({"message": "Face not recognized", "status": "failed"})

            # ✅ Correct identity extraction from folder name
            name = os.path.basename(os.path.dirname(identity_path))
            name = name.strip().lower()
            print("Detected name after normalization:", name)

            # ⚠ Handle duplicate names safely
            persons = Person.objects.filter(name__iexact=name)

            if not persons.exists():
                return JsonResponse({
                    "message": "User not registered",
                    "status": "failed"
                })

            # If multiple users exist, pick the first (temporary fix)
            person = persons.first()

            if persons.count() > 1:
                print(f"⚠ Duplicate users found for name: {name}")

            # Get subject (optional)
            subject = None
            if subject_name:
                subject, _ = Subject.objects.get_or_create(name=subject_name)

            # Check if already checked in today
            already_checked = Attendance.objects.filter(
                person=person,
                subject=subject,
                date=localdate()
            ).exists()

            if already_checked:
                return JsonResponse({
                    "name": name,
                    "message": f"{name} already marked present today",
                    "status": "duplicate"
                })

            # Otherwise create new record
            Attendance.objects.create(
                person=person,
                subject=subject,
                status="IN",
                date=localdate()
            )

            return JsonResponse({
                "name": name,
                "message": "Check-in successful",
                "status": "success"
            })

        except Exception as e:
            return JsonResponse({
                "message": "Recognition error: " + str(e),
                "status": "failed"
            })


def home(request):
    return render(request, 'index.html')



from django.utils.timezone import localdate
from django.db.models import Count


def get_attendance(request):
    records = Attendance.objects.select_related('person', 'subject').all()

    data = []
    for r in records:
        data.append({
            "id": r.id,
            "name": r.person.name,
            "subject": r.subject.name if r.subject else "N/A",
            "time": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "status": r.status
        })

    today = localtime().date()

    # ✅ Today present count
    today_records = Attendance.objects.filter(timestamp__date=today)
    today_present = today_records.count()

    # ❗ Simple logic (you can improve later)
    total_students = Person.objects.count()
    today_absent = max(total_students - today_present, 0)

    # ✅ Student summary
    summary = records.values('person__name').annotate(count=Count('id'))
    student_summary = {
        item['person__name']: item['count'] for item in summary
    }

    # ✅ Monthly percentage (simple version)
    monthly_percentage = {}
    for student in student_summary:
        monthly_percentage[student] = round((student_summary[student] / 30) * 100, 2)

    return JsonResponse({
        "data": data,
        "today_present": today_present,
        "today_absent": today_absent,
        "student_summary": student_summary,
        "monthly_percentage": monthly_percentage
    })

def download_csv(request):
    records = Attendance.objects.select_related('person').all()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance.csv"'

    response.write("Name,Time,Status\n")

    for r in records:
        response.write(f"{r.person.name},{r.timestamp},{r.status}\n")

    return response


# Register endpoint for adding new users with image and name
@csrf_exempt
def register(request):
    if request.method == "POST":
        try:
            name = request.POST.get("name").strip().lower()
            image_data = request.POST.get("image")

            if not name or not image_data:
                return JsonResponse({"message": "Missing data"})

            # Decode image
            img_bytes = base64.b64decode(image_data)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            # 🔥 Save image to folder (IMPORTANT)
            folder_path = os.path.join(settings.BASE_DIR, "ImagesAttendance")

            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

            from datetime import datetime
            # Create user-specific folder
            user_folder = os.path.join(folder_path, name)
            if not os.path.exists(user_folder):
                os.makedirs(user_folder)

            # 🔍 Skip blurry images (Laplacian variance)
            def is_blurry(image, threshold=100):
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                variance = cv2.Laplacian(gray, cv2.CV_64F).var()
                return variance < threshold

            if is_blurry(img):
                return JsonResponse({"message": "Image too blurry, try again", "status": "failed"})

            # 🔁 Skip duplicate images (simple histogram comparison)
            def is_duplicate(new_img, existing_path, threshold=0.9):
                existing_img = cv2.imread(existing_path)
                if existing_img is None:
                    return False

                hist1 = cv2.calcHist([new_img], [0], None, [256], [0,256])
                hist2 = cv2.calcHist([existing_img], [0], None, [256], [0,256])

                cv2.normalize(hist1, hist1)
                cv2.normalize(hist2, hist2)

                similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
                return similarity > threshold

            # Check duplicates in user folder
            for file in os.listdir(user_folder):
                path = os.path.join(user_folder, file)
                if path.endswith('.jpg') and is_duplicate(img, path):
                    return JsonResponse({"message": "Duplicate image, try different angle", "status": "failed"})

            # Save multiple images per user with max image limit
            MAX_IMAGES = 5

            # Get existing images sorted by creation time (oldest first)
            existing_images = sorted(
                [os.path.join(user_folder, f) for f in os.listdir(user_folder) if f.endswith('.jpg')],
                key=os.path.getctime
            )

            # If limit reached, delete oldest image
            if len(existing_images) >= MAX_IMAGES:
                os.remove(existing_images[0])

            # Save new image
            file_path = os.path.join(user_folder, f"img_{int(datetime.now().timestamp())}.jpg")
            cv2.imwrite(file_path, img)

            from .models import Person

            # Save user in database if not exists
            person, created = Person.objects.get_or_create(name=name)

            if created:
                message = f"{name} registered successfully"
            else:
                message = f"{name} already exists, image updated"

            return JsonResponse({
                "message": message,
                "status": "success"
            })

        except Exception as e:
            return JsonResponse({
                "message": "Registration failed: " + str(e),
                "status": "error"
            })

    return JsonResponse({
        "message": "Invalid request",
        "status": "error"
    })

@login_required
def admin_dashboard(request):
    return render(request, 'admin_dashboard.html')


# New function for deleting attendance record
import json

@csrf_exempt
def delete_attendance(request):
    if request.method == "POST":
        data = json.loads(request.body)
        record_id = data.get("id")

        try:
            record = Attendance.objects.filter(id=record_id).first()

            if not record:
                return JsonResponse({"message": "Record not found"})

            record.delete()

            return JsonResponse({"message": "Deleted successfully"})

        except Exception as e:
            return JsonResponse({"message": str(e)})

    return JsonResponse({"message": "Invalid request"})