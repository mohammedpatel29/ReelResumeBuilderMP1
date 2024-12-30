"""
AI-powered talent matching service for connecting employers with suitable candidates.
Uses scikit-learn for text vectorization and similarity scoring.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import json
from typing import List, Dict, Tuple, Optional
import logging
from models import User, JobPosting, CandidateMatch, Video, Tag
from extensions import db
import importlib

# Enhanced logging setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class TalentMatchingService:
    def __init__(self):
        """Initialize the service with enhanced error handling and dependency checks"""
        self.is_initialized = False
        self.vectorizer = None
        logger.info("TalentMatchingService instance created")

    def _check_dependencies(self) -> bool:
        """Verify all required dependencies are available"""
        try:
            required_packages = ['sklearn', 'numpy']
            for package in required_packages:
                importlib.import_module(package)
            return True
        except ImportError as e:
            logger.error(f"Missing required dependency: {str(e)}")
            return False

    def initialize(self) -> bool:
        """Initialize the service with proper dependency checks and error handling"""
        if self.is_initialized:
            logger.debug("TalentMatchingService already initialized")
            return True

        try:
            logger.info("Starting TalentMatchingService initialization...")

            # Check dependencies first
            if not self._check_dependencies():
                raise RuntimeError("Required dependencies not available")

            # Initialize vectorizer
            self.vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words='english',
                ngram_range=(1, 2)
            )

            # Verify vectorizer with sample data
            sample_text = [
                "software development programming coding",
                "project management leadership teamwork",
                "data analysis statistics machine learning"
            ]
            self.vectorizer.fit(sample_text)

            # Verify transformation works
            test_transform = self.vectorizer.transform(["test text"])
            if test_transform.shape[1] == 0:
                raise ValueError("Vectorizer transformation failed")

            self.is_initialized = True
            logger.info("TalentMatchingService successfully initialized")
            return True

        except Exception as e:
            self.is_initialized = False
            logger.error(f"Failed to initialize TalentMatchingService: {str(e)}", exc_info=True)
            return False

    def _ensure_initialized(self) -> bool:
        """Ensure service is initialized before use"""
        if not self.is_initialized:
            return self.initialize()
        return True

    def create_candidate_profile_embedding(self, candidate: User) -> Optional[np.ndarray]:
        """Generate embedding for a candidate's profile including videos and tags"""
        if not self._ensure_initialized():
            logger.error("Failed to initialize service for candidate embedding")
            return None

        try:
            logger.debug(f"Creating embedding for candidate {candidate.id}")
            profile_text = []

            if candidate.first_name and candidate.last_name:
                profile_text.append(f"{candidate.first_name} {candidate.last_name}")

            for video in candidate.videos:
                if video.title:
                    profile_text.append(video.title)
                if video.description:
                    profile_text.append(video.description)
                video_tags = [tag.name for tag in video.tags]
                if video_tags:
                    profile_text.append(" ".join(video_tags))

            if not profile_text:
                logger.warning(f"No profile text found for candidate {candidate.id}")
                return None

            combined_text = " ".join(profile_text)
            embedding = self.vectorizer.transform([combined_text])
            return embedding.toarray()[0]

        except Exception as e:
            logger.error(f"Error generating candidate embedding: {str(e)}", exc_info=True)
            return None

    def create_job_posting_embedding(self, job_posting: JobPosting) -> Optional[np.ndarray]:
        """Generate embedding for a job posting"""
        try:
            self._ensure_initialized()
            logger.debug(f"Creating embedding for job posting {job_posting.id}")

            job_text = []

            # Add job information
            job_text.append(job_posting.title)
            job_text.append(job_posting.description)

            if job_posting.requirements:
                job_text.append(job_posting.requirements)
            if job_posting.responsibilities:
                job_text.append(job_posting.responsibilities)

            # Add required and preferred skills
            if job_posting.required_skills:
                job_text.append(" ".join(job_posting.required_skills))
            if job_posting.preferred_skills:
                job_text.append(" ".join(job_posting.preferred_skills))

            if not job_text:
                logger.warning(f"No job text found for posting {job_posting.id}")
                return None

            # Combine all text
            combined_text = " ".join(job_text)
            logger.debug(f"Generated job text of length {len(combined_text)}")

            # Transform the text using the fitted vectorizer
            embedding = self.vectorizer.transform([combined_text])
            return embedding.toarray()[0]

        except Exception as e:
            logger.error(f"Error generating job posting embedding: {str(e)}", exc_info=True)
            return None

    def calculate_match_score(self, candidate_embedding: np.ndarray, job_embedding: np.ndarray) -> float:
        """Calculate similarity score between candidate and job posting"""
        try:
            if candidate_embedding is None or job_embedding is None:
                logger.warning("Received null embedding, returning 0.0 match score")
                return 0.0

            # Reshape embeddings for cosine_similarity
            candidate_embedding = candidate_embedding.reshape(1, -1)
            job_embedding = job_embedding.reshape(1, -1)

            # Calculate cosine similarity
            similarity = cosine_similarity(candidate_embedding, job_embedding)[0][0]
            logger.debug(f"Calculated match score: {similarity}")
            return float(similarity)

        except Exception as e:
            logger.error(f"Error calculating match score: {str(e)}", exc_info=True)
            return 0.0

    def analyze_skill_match(self, candidate: User, job_posting: JobPosting) -> Dict:
        """Analyze how well candidate's skills match job requirements"""
        try:
            logger.debug(f"Analyzing skill match for candidate {candidate.id} and job {job_posting.id}")

            # Collect skills from video tags
            candidate_skills = set()
            for video in candidate.videos:
                candidate_skills.update(tag.name.lower() for tag in video.tags)

            required_skills = set(skill.lower() for skill in job_posting.required_skills)
            preferred_skills = set(skill.lower() for skill in job_posting.preferred_skills)

            # Calculate matches
            matched_required = candidate_skills.intersection(required_skills)
            matched_preferred = candidate_skills.intersection(preferred_skills)

            total_skills = len(required_skills) + len(preferred_skills)
            match_percentage = (
                (len(matched_required) + len(matched_preferred)) / total_skills
                if total_skills > 0 else 0
            )

            logger.debug(f"Skill match analysis complete. Match percentage: {match_percentage}")

            return {
                'matched_required_skills': list(matched_required),
                'matched_preferred_skills': list(matched_preferred),
                'missing_required_skills': list(required_skills - candidate_skills),
                'total_skill_match_percentage': match_percentage
            }

        except Exception as e:
            logger.error(f"Error analyzing skill match: {str(e)}", exc_info=True)
            return {
                'matched_required_skills': [],
                'matched_preferred_skills': [],
                'missing_required_skills': [],
                'total_skill_match_percentage': 0
            }

    def match_candidates_to_job(self, 
                              job_posting: JobPosting, 
                              candidates: List[User], 
                              threshold: float = 0.6) -> List[Tuple[User, float, Dict]]:
        """Find and rank matching candidates for a job posting"""
        try:
            self._ensure_initialized()
            logger.info(f"Starting candidate matching for job {job_posting.id}")

            job_embedding = self.create_job_posting_embedding(job_posting)
            if job_embedding is None:
                raise ValueError(f"Failed to create embedding for job posting {job_posting.id}")

            matches = []
            processed_count = 0

            for candidate in candidates:
                try:
                    # Skip if candidate is not a job seeker
                    if candidate.user_type != 'jobseeker':
                        continue

                    # Generate candidate embedding
                    candidate_embedding = self.create_candidate_profile_embedding(candidate)
                    if candidate_embedding is None:
                        logger.warning(f"Skipping candidate {candidate.id} - failed to create embedding")
                        continue

                    # Calculate match score
                    match_score = self.calculate_match_score(candidate_embedding, job_embedding)

                    # Only include matches above threshold
                    if match_score >= threshold:
                        # Analyze skill matches
                        skill_match_details = self.analyze_skill_match(candidate, job_posting)

                        try:
                            # Create or update CandidateMatch record
                            match_record = CandidateMatch.query.filter_by(
                                job_posting_id=job_posting.id,
                                candidate_id=candidate.id
                            ).first()

                            if match_record is None:
                                match_record = CandidateMatch(
                                    job_posting_id=job_posting.id,
                                    candidate_id=candidate.id,
                                    match_score=match_score,
                                    skill_match_details=skill_match_details
                                )
                                db.session.add(match_record)
                            else:
                                match_record.match_score = match_score
                                match_record.skill_match_details = skill_match_details
                                match_record.updated_at = db.func.now()

                            matches.append((candidate, match_score, skill_match_details))
                            processed_count += 1

                        except Exception as db_error:
                            logger.error(f"Database error processing match for candidate {candidate.id}: {str(db_error)}")
                            db.session.rollback()
                            continue

                except Exception as candidate_error:
                    logger.error(f"Error processing candidate {candidate.id}: {str(candidate_error)}")
                    continue

            try:
                db.session.commit()
                logger.info(f"Successfully processed {processed_count} candidates for job {job_posting.id}")
            except Exception as commit_error:
                logger.error(f"Error committing matches to database: {str(commit_error)}")
                db.session.rollback()

            # Sort matches by score in descending order
            matches.sort(key=lambda x: x[1], reverse=True)
            return matches

        except Exception as e:
            logger.error(f"Error in match_candidates_to_job: {str(e)}", exc_info=True)
            return []

# Initialize the global talent matching service
talent_matcher = TalentMatchingService()