{% extends "base.html" %}
{% block content %}
<h2 class="mb-4">Dashboard</h2>
<div class="row g-3">
    <div class="col-md-3">
        <div class="card shadow-sm p-3 text-center">
            <h5>📁 Uploaded Files</h5>
            <p class="display-6">{{ files|length if files else 0 }}</p>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card shadow-sm p-3 text-center">
            <h5>📊 Models Trained</h5>
            <p class="display-6">0</p>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card shadow-sm p-3 text-center">
            <h5>📈 Reports Generated</h5>
            <p class="display-6">0</p>
        </div>
    </div>
</div>
<div class="mt-5">
    <a href="#" class="btn btn-primary">Upload New Dataset</a>
</div>
{% endblock %}
