#ifndef MINKINDR_CONVERSIONS_KINDR_TF_H
#define MINKINDR_CONVERSIONS_KINDR_TF_H

#include <kindr/minimal/quat-transformation.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Transform.hpp>
#include <tf2/LinearMath/Vector3.hpp>

#include <Eigen/Core>
#include <Eigen/Geometry>
#include <tf2/transform_datatypes.hpp>
#include <tf2_eigen/tf2_eigen.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>

#include <glog/logging.h>
// #include <tf_conversions/tf_eigen.h>

template <typename Scalar>
void quaternionEigenToTF(const Eigen::Quaternion<Scalar>& eigen,
                         tf2::Quaternion& tf_type) {
  tf_type.setX(static_cast<double>(eigen.x()));
  tf_type.setY(static_cast<double>(eigen.y()));
  tf_type.setZ(static_cast<double>(eigen.z()));
  tf_type.setW(static_cast<double>(eigen.w()));
}
template <typename Scalar>
void quaternionTFToEigen(const tf2::Quaternion& tf_type,
                         Eigen::Quaternion<Scalar>& eigen) {
  eigen.x() = static_cast<Scalar>(tf_type.x());
  eigen.y() = static_cast<Scalar>(tf_type.y());
  eigen.z() = static_cast<Scalar>(tf_type.z());
  eigen.w() = static_cast<Scalar>(tf_type.w());
}
template <typename Scalar>
void vectorEigenToTF(const Eigen::Matrix<Scalar, 3, 1>& eigen,
                     tf2::Vector3& tf_type) {
  tf_type.setX(static_cast<double>(eigen.x()));
  tf_type.setY(static_cast<double>(eigen.y()));
  tf_type.setZ(static_cast<double>(eigen.z()));
}
template <typename Scalar>
void vectorTFToEigen(const tf2::Vector3& tf_type,
                     Eigen::Matrix<Scalar, 3, 1>& eigen) {
  eigen.x() = static_cast<Scalar>(tf_type.x());
  eigen.y() = static_cast<Scalar>(tf_type.y());
  eigen.z() = static_cast<Scalar>(tf_type.z());
}

namespace tf {

// A wrapper for the relevant functions in eigen_conversions.
template <typename Scalar>
void quaternionKindrToTF(
    const kindr::minimal::RotationQuaternionTemplate<Scalar>& kindr,
    tf2::Quaternion* tf_type) {
  CHECK_NOTNULL(tf_type);
  quaternionEigenToTF(kindr.toImplementation(), *tf_type);
}

template <typename Scalar>
void quaternionTFToKindr(
    const tf2::Quaternion& tf_type,
    kindr::minimal::RotationQuaternionTemplate<Scalar>* kindr) {
  CHECK_NOTNULL(kindr);
  Eigen::Quaternion<Scalar> quat;
  quaternionTFToEigen(tf_type, quat);
  *kindr = kindr::minimal::RotationQuaternionTemplate<Scalar>(quat);
}
// Also the Eigen implementation version of this.
template <typename Scalar>
void quaternionKindrToTF(const Eigen::Quaternion<Scalar>& kindr,
                         tf2::Quaternion* tf_type) {
  CHECK_NOTNULL(tf_type);
  quaternionEigenToTF(kindr, *tf_type);
}

template <typename Scalar>
void quaternionTFToKindr(const tf2::Quaternion& tf_type,
                         Eigen::Quaternion<Scalar>* kindr) {
  CHECK_NOTNULL(kindr);
  Eigen::Quaterniond kindr_double;
  quaternionTFToEigen(tf_type, kindr_double);
  *kindr = kindr_double.cast<Scalar>();
}

// A wrapper for the relevant functions in eigen_conversions.
template <typename Scalar>
void vectorKindrToTF(const Eigen::Matrix<Scalar, 3, 1>& kindr,
                     tf2::Vector3* tf_type) {
  CHECK_NOTNULL(tf_type);
  vectorEigenToTF(kindr, *tf_type);
}

template <typename Scalar>
void vectorTFToKindr(const tf2::Vector3& tf_type,
                     Eigen::Matrix<Scalar, 3, 1>* kindr) {
  CHECK_NOTNULL(kindr);
  Eigen::Matrix<double, 3, 1> kindr_double;
  vectorTFToEigen(tf_type, kindr_double);
  *kindr = kindr_double.cast<Scalar>();
}

// Convert a kindr::minimal::QuatTransformation to a geometry_msgs::Transform.
template <typename Scalar>
void transformKindrToTF(
    const kindr::minimal::QuatTransformationTemplate<Scalar>& kindr,
    tf2::Transform* tf_type) {
  CHECK_NOTNULL(tf_type);
  tf2::Vector3 origin;
  tf2::Quaternion rotation;
  vectorKindrToTF(kindr.getPosition(), &origin);
  quaternionKindrToTF(kindr.getRotation(), &rotation);
  tf_type->setOrigin(origin);
  tf_type->setRotation(rotation);
}

template <typename Scalar>
void transformTFToKindr(
    const tf2::Transform& tf_type,
    kindr::minimal::QuatTransformationTemplate<Scalar>* kindr) {
  CHECK_NOTNULL(kindr);
  Eigen::Matrix<Scalar, 3, 1> position;
  Eigen::Quaternion<Scalar> rotation;

  quaternionTFToKindr(tf_type.getRotation(), &rotation);
  vectorTFToKindr(tf_type.getOrigin(), &position);

  // Enforce positive w.
  if (rotation.w() < 0) {
    rotation.coeffs() = -rotation.coeffs();
  }

  *kindr =
      kindr::minimal::QuatTransformationTemplate<Scalar>(rotation, position);
}

// Convert a kindr::minimal::QuatTransformation to a 6 DoF geometry msgs pose.
template <typename Scalar>
void poseKindrToTF(
    const kindr::minimal::QuatTransformationTemplate<Scalar>& kindr,
    tf2::Transform* tf_type) {
  transformKindrToTF(kindr, tf_type);
}

template <typename Scalar>
void poseTFToKindr(const tf2::Transform& tf_type,
                   kindr::minimal::QuatTransformationTemplate<Scalar>* kindr) {
  transformTFToKindr(tf_type, kindr);
}

}  // namespace tf

#endif  // MINKINDR_CONVERSIONS_KINDR_TF_H
